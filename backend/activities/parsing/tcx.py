"""Reads the summary of an activity from a TCX file (Garmin Training Center XML).

TCX is XML from untrusted hands, so this reader does what the usual XML attacks need to be
impossible: it uses expat directly, refuses every document that has a ``DOCTYPE`` (and with it
entity declarations, so nothing is ever expanded or fetched), reads the file as a stream without
building a tree, keeps only short texts of the few elements it wants, and caps nesting, element
and trackpoint counts. The handlers only record raw strings; the summary is computed afterwards.

The summary holds what the laps report: sums over the laps where every lap reports the value, and
a lap-time weighted average for heart rate and power. If one lap lacks a value, the value stays
empty instead of being estimated.
"""

import xml.parsers.expat as expat
from datetime import datetime, timedelta
from typing import Any, Protocol

from . import values
from .types import (
    CYCLING,
    MAX_LAPS,
    OTHER,
    RUNNING,
    TCX_FILE,
    InvalidFileError,
    ParsedActivity,
    ParsedLap,
    UnsupportedFileError,
)

MAX_TRACKPOINTS = 250_000
MAX_ELEMENTS = 5_000_000
MAX_DEPTH = 64
_MAX_TEXT = 64  # longer texts are not numbers, times or names we want
_CHUNK = 64 * 1024

_ROOT = "TrainingCenterDatabase"
_SPORTS = {"Running": RUNNING, "Biking": CYCLING}
_LAP_FIELDS = {"TotalTimeSeconds", "DistanceMeters", "Calories"}
_LAP_HEART_RATES = {"AverageHeartRateBpm", "MaximumHeartRateBpm"}


def parse_tcx(data: bytes) -> ParsedActivity:
    reader = _Reader()
    feed(data, reader)
    return reader.summary()


class Handlers(Protocol):
    def start(self, name: str, attributes: dict[str, str]) -> None: ...
    def end(self, name: str) -> None: ...
    def text(self, data: str) -> None: ...


def feed(data: bytes, handlers: Handlers) -> None:
    """Stream ``data`` through expat into ``handlers``, with the protections described above."""
    # Some exporters put a line break before the XML declaration, which strict XML forbids.
    trimmed = data.lstrip(b" \t\r\n")
    if trimmed.startswith(b"<"):
        data = trimmed
    parser = expat.ParserCreate(namespace_separator="}")
    parser.buffer_text = True
    parser.StartElementHandler = handlers.start
    parser.EndElementHandler = handlers.end
    parser.CharacterDataHandler = handlers.text
    parser.StartDoctypeDeclHandler = _refuse_doctype
    try:
        for offset in range(0, len(data), _CHUNK):
            parser.Parse(data[offset : offset + _CHUNK], False)
        parser.Parse(b"", True)
    except expat.ExpatError, UnicodeError:
        raise InvalidFileError("The TCX file is not well-formed XML.") from None
    except LookupError as error:
        if isinstance(error, IndexError | KeyError):
            raise  # a bug in this module, not a bad file: it must not look like one
        raise InvalidFileError("The TCX file uses an encoding that is not supported.") from None


def _refuse_doctype(*_: Any) -> None:
    raise InvalidFileError("The TCX file must not contain a document type declaration.")


def _local(name: str) -> str:
    return name.rpartition("}")[2]


def _moment(text: str) -> datetime | None:
    try:
        return values.moment(datetime.fromisoformat(text))
    except ValueError:
        return None


def _number(text: str | None) -> float | None:
    try:
        return float(text) if text else None
    except ValueError:
        return None


class _Reader:
    def __init__(self) -> None:
        self.stack: list[str] = []
        self.elements = 0
        self.activities = 0
        self.sport = ""
        self.activity_id = ""
        self.creator = ""
        self.laps: list[dict[str, str]] = []
        self.trackpoints = 0
        self.first_time: datetime | None = None
        self.last_time: datetime | None = None
        self._lap_depth: int | None = None  # depth of the lap that is being read
        self._capture: tuple[str, str] | None = None
        self._capture_depth = 0
        self._text: list[str] = []
        self._text_length = 0

    def start(self, name: str, attributes: dict[str, str]) -> None:
        self.elements += 1
        if self.elements > MAX_ELEMENTS:
            raise InvalidFileError("The TCX file contains too much data.")
        local = _local(name)
        if not self.stack and local != _ROOT:
            raise UnsupportedFileError("This XML file is not a TCX activity file.")
        if len(self.stack) >= MAX_DEPTH:
            raise InvalidFileError("The TCX file is nested too deeply.")
        parent = self.stack[-1] if self.stack else ""
        self.stack.append(local)
        depth = len(self.stack)

        capture: tuple[str, str] | None = None
        if local == "MultiSportSession":
            raise UnsupportedFileError("The file contains several sports in one session.")
        if local == "Activity" and parent == "Activities":
            self.activities += 1
            if self.activities > 1:
                raise UnsupportedFileError("The file contains several activities.")
            self.sport = attributes.get("Sport", "")[:50]
        elif local == "Lap" and parent == "Activity":
            if len(self.laps) >= MAX_LAPS:
                raise InvalidFileError("The file contains too many laps.")
            self.laps.append({"StartTime": attributes.get("StartTime", "")[:_MAX_TEXT]})
            self._lap_depth = len(self.stack)
        elif local == "Trackpoint":
            self.trackpoints += 1
            if self.trackpoints > MAX_TRACKPOINTS:
                raise InvalidFileError("The TCX file contains too much data.")
        elif self._lap_depth is not None and local in _LAP_FIELDS and depth == self._lap_depth + 1:
            capture = ("lap", local)
        elif (
            self._lap_depth is not None
            and local == "Value"
            and parent in _LAP_HEART_RATES
            and depth == self._lap_depth + 2
        ):
            capture = ("lap", parent)
        elif (
            self._lap_depth is not None
            and local == "AvgWatts"
            and parent == "LX"
            and depth == self._lap_depth + 3
        ):
            capture = ("lap", "AvgWatts")
        elif local == "Time" and parent == "Trackpoint":
            capture = ("time", "")
        elif local == "Name" and parent == "Creator":
            capture = ("creator", "")
        elif local == "Id" and parent == "Activity":
            capture = ("id", "")

        if capture is not None and self._capture is None:
            self._capture = capture
            self._capture_depth = len(self.stack)
            self._text = []
            self._text_length = 0

    def text(self, data: str) -> None:
        if self._capture is not None and self._text_length < _MAX_TEXT:
            piece = data[: _MAX_TEXT - self._text_length]
            self._text.append(piece)
            self._text_length += len(piece)

    def end(self, name: str) -> None:
        if self._capture is not None and self._capture_depth == len(self.stack):
            kind, key = self._capture
            value = "".join(self._text).strip()
            self._capture = None
            if kind == "lap":
                self.laps[-1].setdefault(key, value)
            elif kind == "time":
                moment = _moment(value)
                if moment is not None:
                    self.first_time = min(self.first_time or moment, moment)
                    self.last_time = max(self.last_time or moment, moment)
            elif kind == "creator":
                self.creator = value
            elif kind == "id":
                self.activity_id = value
        if self._lap_depth == len(self.stack):
            self._lap_depth = None
        self.stack.pop()

    def summary(self) -> ParsedActivity:
        if self.activities == 0:
            raise UnsupportedFileError("The TCX file contains no activity.")
        if not self.laps:
            raise UnsupportedFileError("The TCX file contains no laps.")

        laps = tuple(
            ParsedLap(
                start_time=_moment(lap["StartTime"]),
                elapsed_seconds=values.seconds(_number(lap.get("TotalTimeSeconds"))),
                distance_m=values.metres(_number(lap.get("DistanceMeters"))),
                avg_heart_rate=values.heart_rate(_number(lap.get("AverageHeartRateBpm"))),
                max_heart_rate=values.heart_rate(_number(lap.get("MaximumHeartRateBpm"))),
            )
            for lap in self.laps
        )
        start = laps[0].start_time or _moment(self.activity_id) or self.first_time
        if start is None:
            raise InvalidFileError("The TCX file has no start time.")

        seconds = [lap.elapsed_seconds for lap in laps]
        timer = _total(seconds)
        return ParsedActivity(
            source=TCX_FILE,
            sport=_SPORTS.get(self.sport, OTHER),
            source_sport=self.sport,
            start_time=start,
            elapsed_seconds=self._elapsed(start, laps),
            timer_seconds=values.seconds(timer),
            distance_m=values.metres(_total([lap.distance_m for lap in laps])),
            avg_heart_rate=values.heart_rate(
                _weighted([lap.avg_heart_rate for lap in laps], seconds)
            ),
            max_heart_rate=values.heart_rate(_highest([lap.max_heart_rate for lap in laps])),
            avg_power_w=values.power(
                _weighted([_number(lap.get("AvgWatts")) for lap in self.laps], seconds)
            ),
            total_ascent_m=None,  # TCX has no ascent total; computing it from altitude would guess
            calories=values.calories(_total([_number(lap.get("Calories")) for lap in self.laps])),
            manufacturer=values.text(self.creator),
            laps=laps,
        )

    def _elapsed(self, start: datetime, laps: tuple[ParsedLap, ...]) -> float | None:
        """From the start to the last moment the file reports; pauses are included."""
        ends = [self.last_time] if self.last_time else []
        last = laps[-1]
        if last.start_time and last.elapsed_seconds is not None:
            ends.append(last.start_time + timedelta(seconds=last.elapsed_seconds))
        return values.seconds((max(ends) - start).total_seconds()) if ends else None


def _total(numbers: list[float | None]) -> float | None:
    """The sum, only if every lap reports a value."""
    return None if any(n is None for n in numbers) else sum(n for n in numbers if n is not None)


def _highest(numbers: list[int | None]) -> int | None:
    return None if any(n is None for n in numbers) else max(n for n in numbers if n is not None)


def _weighted(numbers: list[Any], seconds: list[float | None]) -> float | None:
    """Average weighted by lap time, only if every lap reports both values."""
    if any(n is None for n in numbers) or any(s is None for s in seconds):
        return None
    total = sum(s for s in seconds if s is not None)
    if total <= 0:
        return None
    return sum(n * s for n, s in zip(numbers, seconds, strict=True) if s is not None) / total
