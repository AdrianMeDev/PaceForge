"""Reads the time series of an activity file: time, power, distance and heart rate per sample.

The summary parsers keep only totals; this reader is used to find the best efforts. The same
safety applies: the CRC is verified, the number of messages is capped, and every failure of the
library becomes an ``InvalidFileError`` with a fixed text. The series is never stored.
"""

import io
from datetime import datetime
from typing import Any

import fitdecode

from ..efforts import Sample
from .fit import MAX_MESSAGES
from .tcx import MAX_DEPTH, MAX_ELEMENTS, MAX_TRACKPOINTS, feed
from .types import ActivityFileError, InvalidFileError, UnsupportedFileError


def fit_series(data: bytes) -> list[Sample]:
    """The records of a FIT file, with the seconds counted from the first record that has a time."""
    if len(data) < 12 or data[8:12] != b".FIT":
        raise UnsupportedFileError("This is not a FIT file.")
    records: list[tuple[datetime, Any, Any, Any]] = []
    messages = headers = 0
    try:
        with fitdecode.FitReader(
            io.BytesIO(data),
            check_crc=fitdecode.CrcCheck.RAISE,
            error_handling=fitdecode.ErrorHandling.RAISE,
        ) as reader:
            for frame in reader:
                if isinstance(frame, fitdecode.FitHeader):
                    headers += 1
                    if headers > 1:
                        raise UnsupportedFileError("The file contains several FIT files.")
                elif isinstance(frame, fitdecode.FitDataMessage):
                    messages += 1
                    if messages > MAX_MESSAGES:
                        raise InvalidFileError("The file contains too much data.")
                    if frame.name != "record":
                        continue
                    moment = frame.get_value("timestamp", fallback=None)
                    if isinstance(moment, datetime):
                        records.append(
                            (
                                moment,
                                frame.get_value("power", fallback=None),
                                frame.get_value("distance", fallback=None),
                                frame.get_value("heart_rate", fallback=None),
                            )
                        )
    except ActivityFileError:
        raise
    except Exception:  # the library, on damaged or hostile input: whatever it raises
        raise InvalidFileError("The FIT file is damaged or incomplete.") from None

    if not records:
        return []
    first = min(moment for moment, *_ in records)
    return [
        Sample(
            seconds=(moment - first).total_seconds(),
            power=_number(power),
            distance=_number(distance),
            heart_rate=_number(heart_rate),
        )
        for moment, power, distance, heart_rate in records
    ]


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


_MAX_TEXT = 64
_ROOT = "TrainingCenterDatabase"


def tcx_series(data: bytes) -> list[Sample]:
    """The trackpoints of a TCX file (time, distance, heart rate, watts), seconds from the first.

    Read with the same protections as the summary: no ``DOCTYPE``, streaming, capped counts.
    """
    reader = _TrackpointReader()
    feed(data, reader)
    points = [point for point in reader.points if point[0] is not None]
    if not points:
        return []
    first = min(moment for moment, *_ in points if moment is not None)
    return [
        Sample(
            seconds=(moment - first).total_seconds(),
            power=watts,
            distance=distance,
            heart_rate=heart_rate,
        )
        for moment, distance, heart_rate, watts in points
        if moment is not None
    ]


Point = tuple[datetime | None, float | None, float | None, float | None]


class _TrackpointReader:
    def __init__(self) -> None:
        self.stack: list[str] = []
        self.elements = 0
        self.points: list[Point] = []
        self._current: dict[str, str] | None = None
        self._capture: str | None = None
        self._capture_depth = 0
        self._text: list[str] = []
        self._text_length = 0

    def start(self, name: str, attributes: dict[str, str]) -> None:
        self.elements += 1
        if self.elements > MAX_ELEMENTS:
            raise InvalidFileError("The TCX file contains too much data.")
        local = name.rpartition("}")[2]
        if not self.stack and local != _ROOT:
            raise UnsupportedFileError("This XML file is not a TCX activity file.")
        if len(self.stack) >= MAX_DEPTH:
            raise InvalidFileError("The TCX file is nested too deeply.")
        parent = self.stack[-1] if self.stack else ""
        grandparent = self.stack[-2] if len(self.stack) > 1 else ""
        self.stack.append(local)

        if local == "Trackpoint":
            if len(self.points) >= MAX_TRACKPOINTS:
                raise InvalidFileError("The TCX file contains too much data.")
            self._current = {}
            return
        if self._current is None or self._capture is not None:
            return
        if parent == "Trackpoint" and local in ("Time", "DistanceMeters"):
            self._capture = local
        elif local == "Value" and parent == "HeartRateBpm" and grandparent == "Trackpoint":
            self._capture = "HeartRateBpm"
        elif local == "Watts" and parent == "TPX":
            self._capture = "Watts"
        if self._capture is not None:
            self._capture_depth = len(self.stack)
            self._text = []
            self._text_length = 0

    def text(self, data: str) -> None:
        if self._capture is not None:
            room = _MAX_TEXT - self._text_length
            if room > 0:
                piece = data[:room]
                self._text.append(piece)
                self._text_length += len(piece)

    def end(self, name: str) -> None:
        if self._capture is not None and self._capture_depth == len(self.stack):
            if self._current is not None:
                self._current.setdefault(self._capture, "".join(self._text).strip())
            self._capture = None
        if self.stack and self.stack[-1] == "Trackpoint" and self._current is not None:
            values = self._current
            self.points.append(
                (
                    _moment(values.get("Time")),
                    _text_number(values.get("DistanceMeters")),
                    _text_number(values.get("HeartRateBpm")),
                    _text_number(values.get("Watts")),
                )
            )
            self._current = None
        self.stack.pop()


def _moment(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    return moment if moment.tzinfo is not None else None


def _text_number(text: str | None) -> float | None:
    try:
        return float(text) if text else None
    except ValueError:
        return None
