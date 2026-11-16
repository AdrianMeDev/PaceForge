"""Reads an activity from a GPX file (what a phone app records, and what Strava keeps of it).

GPX is XML from untrusted hands, so it is read the way TCX is (``tcx.feed``): expat directly, no
``DOCTYPE``, a stream without a tree, short texts of the few elements wanted, capped nesting,
element and point counts.

A GPX file is a list of points with a place and a time and, where the app wrote it, a heart rate
(the ``hr`` of the Garmin extension). It has no laps, no sport of the athlete's own (only the type
of the track, if the app wrote one), no power and no totals: the duration is the time from the first
to the last point, the distance is added up from the points (great circle, so about as good as the
GPS), the heart rate is the mean of the points that have one. The moving time is not known and not
guessed.
"""

import math
from datetime import datetime

from ..efforts import Sample
from . import values
from .tcx import MAX_DEPTH, MAX_ELEMENTS, MAX_TRACKPOINTS, feed
from .types import (
    CYCLING,
    GPX_FILE,
    OTHER,
    RUNNING,
    SWIMMING,
    InvalidFileError,
    ParsedActivity,
    UnsupportedFileError,
)

_ROOT = "gpx"
_MAX_TEXT = 64
_EARTH_RADIUS_M = 6_371_008.8
# The track types that apps write (Strava writes its own words); anything else is ``other``.
_SPORTS = {
    "running": RUNNING,
    "run": RUNNING,
    "trail_run": RUNNING,
    "trailrun": RUNNING,
    "virtualrun": RUNNING,
    "walking": OTHER,
    "cycling": CYCLING,
    "biking": CYCLING,
    "ride": CYCLING,
    "virtualride": CYCLING,
    "swimming": SWIMMING,
    "swim": SWIMMING,
}

# (time, latitude, longitude, heart rate)
_Point = tuple[datetime | None, float | None, float | None, float | None]


def parse_gpx(data: bytes) -> ParsedActivity:
    reader = _Reader()
    feed(data, reader, "GPX")
    return reader.summary()


def gpx_series(data: bytes) -> list[Sample]:
    """The points of a GPX file with a time: seconds from the first, metres from the start (added
    up from the points) and heart rate. Read with the same protections as the summary."""
    reader = _Reader()
    feed(data, reader, "GPX")
    return reader.series()


def distance_between(a: tuple[float, float], b: tuple[float, float]) -> float:
    """The great-circle distance in metres between two points given as (latitude, longitude)."""
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    half = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * _EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(half)))


def _moment(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    return values.moment(moment) if moment.tzinfo is not None else None


def _number(text: str | None) -> float | None:
    try:
        number = float(text) if text else None
    except ValueError:
        return None
    return number if number is not None and math.isfinite(number) else None


class _Reader:
    def __init__(self) -> None:
        self.stack: list[str] = []
        self.elements = 0
        self.creator = ""
        self.track_type = ""
        self.points: list[_Point] = []
        self._current: dict[str, str] | None = None
        self._capture: str | None = None
        self._capture_depth = 0
        self._text: list[str] = []
        self._text_length = 0

    def start(self, name: str, attributes: dict[str, str]) -> None:
        self.elements += 1
        if self.elements > MAX_ELEMENTS:
            raise InvalidFileError("The GPX file contains too much data.")
        local = name.rpartition("}")[2]
        if not self.stack and local != _ROOT:
            raise UnsupportedFileError("This XML file is not a GPX activity file.")
        if len(self.stack) >= MAX_DEPTH:
            raise InvalidFileError("The GPX file is nested too deeply.")
        parent = self.stack[-1] if self.stack else ""
        self.stack.append(local)

        if not parent:
            self.creator = attributes.get("creator", "")[:_MAX_TEXT]
            return
        if local == "trkpt":
            if len(self.points) >= MAX_TRACKPOINTS:
                raise InvalidFileError("The GPX file contains too much data.")
            self._current = {
                "lat": attributes.get("lat", "")[:_MAX_TEXT],
                "lon": attributes.get("lon", "")[:_MAX_TEXT],
            }
            return
        if self._capture is not None:
            return
        if self._current is not None and ((local == "time" and parent == "trkpt") or local == "hr"):
            self._capture = local
        elif self._current is None and local == "type" and parent == "trk":
            self._capture = "type"
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
            text = "".join(self._text).strip()
            if self._capture == "type":
                self.track_type = self.track_type or text
            elif self._current is not None:
                self._current.setdefault(self._capture, text)
            self._capture = None
        if self.stack and self.stack[-1] == "trkpt" and self._current is not None:
            current = self._current
            self.points.append(
                (
                    _moment(current.get("time")),
                    _coordinate(current.get("lat"), 90),
                    _coordinate(current.get("lon"), 180),
                    _number(current.get("hr")),
                )
            )
            self._current = None
        self.stack.pop()

    def timed(self) -> list[_Point]:
        found = [point for point in self.points if point[0] is not None]
        if len(found) < 2:
            raise InvalidFileError("The GPX file has no track with time stamps.")
        return found

    def summary(self) -> ParsedActivity:
        timed = self.timed()
        times = [moment for moment, *_ in timed if moment is not None]
        start, end = min(times), max(times)
        beats = [rate for *_, rate in timed if rate is not None]
        kind = self.track_type.strip().lower().replace(" ", "")
        return ParsedActivity(
            source=GPX_FILE,
            sport=_SPORTS.get(kind, OTHER),
            source_sport=self.track_type[:50],
            start_time=start,
            elapsed_seconds=values.seconds((end - start).total_seconds()),
            # the moving time of a GPX file is not known: a pause and a stop look the same
            timer_seconds=None,
            distance_m=values.metres(_distance(timed)),
            avg_heart_rate=values.heart_rate(sum(beats) / len(beats)) if beats else None,
            max_heart_rate=values.heart_rate(max(beats)) if beats else None,
            manufacturer=values.text(self.creator),
        )

    def series(self) -> list[Sample]:
        timed = self.timed()
        first = min(moment for moment, *_ in timed if moment is not None)
        samples: list[Sample] = []
        travelled = 0.0
        previous: tuple[float, float] | None = None
        for moment, lat, lon, rate in sorted(timed, key=lambda point: point[0] or first):
            if moment is None:
                continue
            if lat is not None and lon is not None:
                if previous is not None:
                    travelled += distance_between(previous, (lat, lon))
                previous = (lat, lon)
            samples.append(
                Sample(
                    seconds=(moment - first).total_seconds(),
                    distance=travelled if previous is not None else None,
                    heart_rate=rate,
                )
            )
        return samples


def _coordinate(text: str | None, limit: float) -> float | None:
    number = _number(text)
    return number if number is not None and -limit <= number <= limit else None


def _distance(points: list[_Point]) -> float | None:
    """The distance added up from the points that have a place, in the order of their time; ``None``
    if fewer than two have one."""
    placed = [
        (moment, (lat, lon))
        for moment, lat, lon, _ in points
        if moment is not None and lat is not None and lon is not None
    ]
    if len(placed) < 2:
        return None
    placed.sort(key=lambda item: item[0])
    return sum(distance_between(a[1], b[1]) for a, b in zip(placed, placed[1:], strict=False))
