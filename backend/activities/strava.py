"""The activity list (``activities.csv``) of a Strava bulk export.

Strava's export is a ZIP with an ``activities`` folder (the recorded files, most of them
gzip-compressed) and ``activities.csv``, one line per activity with its type, its start and, where
there is a recording, the name of the file. This module reads that list. It is pure: no database,
no files.

The list is read by the names of its columns, not by their places. Strava writes some names twice
(``Elapsed Time`` and ``Distance`` are in the list a second time, in seconds and metres). The first
``Elapsed Time`` is seconds; of the two ``Distance`` columns the second is metres and the first
kilometres, and if there is only one it is read as kilometres. Whatever cannot be read (a date of
another language, a number that is no number) makes that line "unreadable": it is counted, never
guessed and never part of a message. The names of the activities and their descriptions are not
read: they are free text and not needed.

The column names are English. An export of an account in another language has other names and is
refused as a whole with a fixed text.
"""

import csv
import io
from dataclasses import dataclass
from datetime import UTC, datetime

from .parsing import values
from .parsing.types import CYCLING, OTHER, RUNNING, STRENGTH, SWIMMING

MAX_ROWS = 100_000
_MAX_FIELD = 1_000
_REQUIRED = ("Activity ID", "Activity Date", "Activity Type")

# What Strava calls its activity types (also those it has renamed over the years) and the sport
# of PaceForge. Everything else (walks, hikes, yoga, skiing, …) is ``other``.
SPORTS = {
    "Run": RUNNING,
    "Trail Run": RUNNING,
    "Virtual Run": RUNNING,
    "Ride": CYCLING,
    "Virtual Ride": CYCLING,
    "E-Bike Ride": CYCLING,
    "Mountain Bike Ride": CYCLING,
    "E-Mountain Bike Ride": CYCLING,
    "Gravel Ride": CYCLING,
    "Handcycle": CYCLING,
    "Velomobile": CYCLING,
    "Swim": SWIMMING,
    "Weight Training": STRENGTH,
}

_MONTHS = {
    name: number
    for number, name in enumerate(
        ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"), 1
    )
}


class StravaListError(Exception):
    """The list as a whole cannot be read. The message is a fixed text, never from the file."""


@dataclass(frozen=True)
class StravaRow:
    """One line of the list. ``filename`` is the path inside the export (``activities/123.fit.gz``)
    and ``None`` for a session that was entered by hand at Strava and has no recording."""

    activity_id: str
    start: datetime
    strava_type: str
    sport: str
    elapsed_seconds: float | None
    distance_m: float | None
    filename: str | None


@dataclass(frozen=True)
class StravaList:
    rows: tuple[StravaRow, ...]
    unreadable: int


def sport_of(strava_type: str) -> str:
    return SPORTS.get(strava_type, OTHER)


def read_activity_list(data: bytes) -> StravaList:
    """The lines of ``activities.csv`` (UTF-8, with or without a byte order mark).

    Raises ``StravaListError`` if it is no such list: not text, no header, a column missing, too
    many lines. A line that cannot be read is counted in ``unreadable`` and left out.
    """
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise StravaListError("The activity list is not UTF-8 text.") from None
    rows = csv.reader(io.StringIO(text, newline=""))
    try:
        header = next(rows, None)
    except csv.Error:
        raise StravaListError("The activity list is not a CSV file.") from None
    if header is None:
        raise StravaListError("The activity list is empty.")
    names = [name.strip() for name in header]
    if any(name not in names for name in _REQUIRED):
        raise StravaListError(
            "The activity list has not the columns of a Strava export "
            "(Activity ID, Activity Date, Activity Type). Is the account set to English?"
        )
    columns = _Columns(names)

    found: list[StravaRow] = []
    unreadable = 0
    count = 0
    while True:
        try:
            fields = next(rows, None)
        except csv.Error:
            unreadable += 1  # a line with a field that is much too large, or a broken quote
            count += 1
            continue
        if fields is None:
            break
        if not any(field.strip() for field in fields):
            continue  # an empty line is no activity
        count += 1
        if count > MAX_ROWS:
            raise StravaListError("The activity list has too many lines.")
        row = columns.read(fields)
        if row is None:
            unreadable += 1
        else:
            found.append(row)
    return StravaList(rows=tuple(found), unreadable=unreadable)


class _Columns:
    def __init__(self, names: list[str]) -> None:
        self.id = names.index("Activity ID")
        self.date = names.index("Activity Date")
        self.type = names.index("Activity Type")
        self.elapsed = names.index("Elapsed Time") if "Elapsed Time" in names else None
        self.filename = names.index("Filename") if "Filename" in names else None
        distances = [i for i, name in enumerate(names) if name == "Distance"]
        # the last of them is metres where there are two, the only one is kilometres
        self.distance = distances[-1] if distances else None
        self.distance_factor = 1.0 if len(distances) > 1 else 1000.0

    def _field(self, fields: list[str], index: int | None) -> str:
        if index is None or index >= len(fields):
            return ""
        return fields[index].strip()

    def read(self, fields: list[str]) -> StravaRow | None:
        activity_id = self._field(fields, self.id)
        start = _start(self._field(fields, self.date))
        strava_type = self._field(fields, self.type)
        if not activity_id.isdigit() or start is None or not strava_type:
            return None
        if any(len(fields[i]) > _MAX_FIELD for i in (self.id, self.date, self.type)):
            return None
        filename = self._field(fields, self.filename)
        return StravaRow(
            activity_id=activity_id,
            start=start,
            strava_type=strava_type[:50],
            sport=sport_of(strava_type),
            elapsed_seconds=values.seconds(_number(self._field(fields, self.elapsed))),
            distance_m=values.metres(
                _scaled(_number(self._field(fields, self.distance)), self.distance_factor)
            ),
            filename=filename if filename and len(filename) <= _MAX_FIELD else None,
        )


def _scaled(number: float | None, factor: float) -> float | None:
    return None if number is None else number * factor


def _number(text: str) -> float | None:
    try:
        return float(text) if text else None
    except ValueError:
        return None


def _start(text: str) -> datetime | None:
    """``Nov 14, 2026, 7:30:12 AM`` (UTC), read without the locale of the host: the names of the
    months are the English ones Strava writes."""
    try:
        month_day, year, clock = (part.strip() for part in text.split(",", 2))
        month_name, day = month_day.split()
        hours_minutes_seconds, marker = clock.split()
        hour, minute, second = (int(part) for part in hours_minutes_seconds.split(":"))
        if marker not in ("AM", "PM") or not 1 <= hour <= 12:
            return None
        hour = hour % 12 + (12 if marker == "PM" else 0)
        return datetime(int(year), _MONTHS[month_name], int(day), hour, minute, second, tzinfo=UTC)
    except ValueError, KeyError:
        return None
