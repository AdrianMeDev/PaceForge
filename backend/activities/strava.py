"""A Strava bulk export: its activity list (``activities.csv``) and the import of all of it.

Strava's export is a ZIP with an ``activities`` folder (the recorded files, most of them
gzip-compressed) and ``activities.csv``, one line per activity with its type, its start and, where
there is a recording, the name of the file. ``read_activity_list`` reads that list (pure: no
database, no files); ``import_export`` imports the whole export.

The list is read by the names of its columns, not by their places. Strava writes some names twice
(``Elapsed Time`` and ``Distance`` are in the list a second time, in seconds and metres). The first
``Elapsed Time`` is seconds; of the two ``Distance`` columns the second is metres and the first
kilometres, and if there is only one it is read as kilometres. Whatever cannot be read (a date of
another language, a number that is no number) makes that line "unreadable": it is counted, never
guessed and never part of a message. The names of the activities and their descriptions are not
read: they are free text and not needed.

The export comes in the language the archive was requested in. English and German are read: the
names of the columns, the names of the activity types, the way dates are written (``Nov 14, 2026,
7:30:12 AM`` or ``14.11.2026, 07:30:12``, both UTC) and the decimal comma. Any other language is
refused as a whole with a fixed text.
"""

import csv
import io
import os
import zipfile
import zlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import IO

from django.conf import settings

from accounts.models import User
from athletes.estimates import refresh_estimates_safely

from .parsing import ActivityFileError, values
from .parsing.types import CYCLING, OTHER, RUNNING, STRENGTH, SWIMMING
from .serializers import DISTANCE_MAX_KM, DURATION_MAX_MINUTES, EARLIEST
from .services import DuplicateActivityError, FileTooLargeError, enter_activity, import_activity

MAX_ROWS = 100_000
_MAX_FIELD = 1_000
# The names of the columns by language; the first of a list that the file has is the one used.
_ID = ("Activity ID", "Aktivitäts-ID")
_DATE = ("Activity Date", "Aktivitätsdatum")
_TYPE = ("Activity Type", "Aktivitätsart")
_ELAPSED = ("Elapsed Time", "Verstrichene Zeit")
_DISTANCE = ("Distance", "Distanz")
_FILENAME = ("Filename", "Dateiname")

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
    # German. Only "Lauf", "Radfahrt" and "Virtuelle Radfahrt" were seen in a real export; the
    # others are Strava's German names as far as they are known. An unknown name is ``other``.
    "Lauf": RUNNING,
    "Trail-Lauf": RUNNING,
    "Virtueller Lauf": RUNNING,
    "Radfahrt": CYCLING,
    "Virtuelle Radfahrt": CYCLING,
    "E-Bike-Fahrt": CYCLING,
    "Mountainbike-Fahrt": CYCLING,
    "Gravel-Fahrt": CYCLING,
    "Schwimmen": SWIMMING,
    "Krafttraining": STRENGTH,
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
    if any(not any(name in names for name in group) for group in (_ID, _DATE, _TYPE)):
        raise StravaListError(
            "The activity list has not the columns of a Strava export in English or German "
            "(Activity ID, Activity Date, Activity Type)."
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
        # the three of them are there: ``read_activity_list`` has checked
        self.id = _first(names, _ID) or 0
        self.date = _first(names, _DATE) or 0
        self.type = _first(names, _TYPE) or 0
        self.elapsed = _first(names, _ELAPSED)
        self.filename = _first(names, _FILENAME)
        distances = [i for i, name in enumerate(names) if name in _DISTANCE]
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
        if len(filename) > _MAX_FIELD:
            return None
        return StravaRow(
            activity_id=activity_id,
            start=start,
            strava_type=strava_type[:50],
            sport=sport_of(strava_type),
            elapsed_seconds=values.seconds(_number(self._field(fields, self.elapsed))),
            distance_m=values.metres(
                _scaled(_number(self._field(fields, self.distance)), self.distance_factor)
            ),
            filename=filename or None,
        )


def _german_start(text: str) -> datetime | None:
    try:
        day_text, clock = (part.strip() for part in text.split(",", 1))
        day, month, year = (int(part) for part in day_text.split("."))
        hour, minute, second = (int(part) for part in clock.split(":"))
        return datetime(year, month, day, hour, minute, second, tzinfo=UTC)
    except ValueError:
        return None


def _first(names: list[str], group: tuple[str, ...]) -> int | None:
    """The place of the first column of the file that has one of these names."""
    for index, name in enumerate(names):
        if name in group:
            return index
    return None


def _scaled(number: float | None, factor: float) -> float | None:
    return None if number is None else number * factor


def _number(text: str) -> float | None:
    """A number with a point (``25951.7``) or with a decimal comma (``25,95``, ``1.234,5``)."""
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        return float(text) if text else None
    except ValueError:
        return None


def _start(text: str) -> datetime | None:
    """``Nov 14, 2026, 7:30:12 AM`` or ``14.11.2026, 07:30:12`` (UTC), read without the locale of
    the host."""
    german = _german_start(text)
    if german is not None:
        return german
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


# ---- the import of a whole export -----------------------------------------------------------

LIST_NAME = "activities.csv"
MAX_MEMBERS = 200_000
MAX_LIST_BYTES = 64 * 1024 * 1024


class ExportError(Exception):
    """The export as a whole cannot be read (not a ZIP, no list, …). The message is a fixed text."""


@dataclass
class ImportCounts:
    """What an import did, as numbers only (nothing of a file or of the list is in a report)."""

    imported: int = 0  # with a recording
    entered: int = 0  # without one: the line of the list alone
    duplicates: int = 0
    unreadable: int = 0  # a recording that cannot be read, or one that is too large
    missing: int = 0  # the list names a recording the export does not hold
    lines_unreadable: int = 0  # a line of the list that cannot be read

    @property
    def total(self) -> int:
        return (
            self.imported
            + self.entered
            + self.duplicates
            + self.unreadable
            + self.missing
            + self.lines_unreadable
        )


def import_export(
    user: User,
    source: str | os.PathLike[str] | IO[bytes],
    *,
    progress: Callable[[int, int], None] | None = None,
) -> ImportCounts:
    """Import the activities of a Strava bulk export (the ZIP) for ``user``.

    The ZIP is read in memory, one member at a time, never extracted and never trusted: only the
    members the list names are read, each at most ``ACTIVITY_UPLOAD_MAX_BYTES`` after unpacking.
    A recording goes through ``import_activity``, so a duplicate (also one from another source,
    also by hand) is skipped and counted and an import run twice adds nothing; the sport of the
    list is used where the file does not know it. A line without a recording is entered like a
    session by hand. Estimated thresholds are refreshed once at the end.

    ``progress(done, total)`` is called after each line. Raises ``ExportError`` if the ZIP or the
    list is unusable.
    """
    try:
        archive = zipfile.ZipFile(source)
    except FileNotFoundError:
        raise ExportError("The archive file was not found.") from None
    except OSError:
        raise ExportError("The archive file cannot be opened.") from None
    except zipfile.BadZipFile:
        raise ExportError("The file is not a ZIP archive.") from None
    with archive:
        if len(archive.infolist()) > MAX_MEMBERS:
            raise ExportError("The ZIP archive holds too many files.")
        listing = _read_list(archive)
        counts = ImportCounts(lines_unreadable=listing.unreadable)
        rows = sorted(listing.rows, key=lambda row: (row.start, row.activity_id))
        for done, row in enumerate(rows, 1):
            _import_row(user, archive, row, counts)
            if progress is not None:
                progress(done, len(rows))
    if counts.imported or counts.entered:
        refresh_estimates_safely(user)
    return counts


def _read_list(archive: zipfile.ZipFile) -> StravaList:
    try:
        data = _read_member(archive, LIST_NAME, MAX_LIST_BYTES)
    except KeyError:
        raise ExportError(f"The ZIP archive has no {LIST_NAME}.") from None
    except _MemberError:
        raise ExportError(f"{LIST_NAME} cannot be read.") from None
    try:
        return read_activity_list(data)
    except StravaListError as error:
        raise ExportError(str(error)) from None


class _MemberError(Exception):
    """A member that cannot be read: damaged, encrypted or larger than the limit."""


def _read_member(archive: zipfile.ZipFile, name: str, limit: int) -> bytes:
    """The content of the member ``name``, at most ``limit`` bytes of it ever held. ``KeyError`` if
    the archive has no such member. The size the archive declares is not believed."""
    info = archive.getinfo(name)
    if info.is_dir() or info.file_size > limit:
        raise _MemberError
    try:
        with archive.open(info) as member:
            data = member.read(limit + 1)
    except zipfile.BadZipFile, zlib.error, RuntimeError, NotImplementedError, EOFError, OSError:
        # RuntimeError: encrypted; NotImplementedError: a compression method that is not known
        raise _MemberError from None
    if len(data) > limit:
        raise _MemberError
    return data


def _import_row(user: User, archive: zipfile.ZipFile, row: StravaRow, counts: ImportCounts) -> None:
    try:
        if row.filename is None:
            _enter(user, row)
            counts.entered += 1
        else:
            _import_file(user, archive, row)
            counts.imported += 1
    except DuplicateActivityError:
        counts.duplicates += 1
    except _Missing:
        counts.missing += 1
    except ActivityFileError, FileTooLargeError, _MemberError, _Unusable:
        counts.unreadable += 1


class _Missing(Exception):
    pass


class _Unusable(Exception):
    """A line without a recording that is too little to enter."""


def _import_file(user: User, archive: zipfile.ZipFile, row: StravaRow) -> None:
    assert row.filename is not None
    try:
        data = _read_member(archive, row.filename, settings.ACTIVITY_UPLOAD_MAX_BYTES)
    except KeyError:
        raise _Missing from None
    sport = None if row.sport == OTHER else row.sport
    import_activity(user, data, sport=sport)


def _enter(user: User, row: StravaRow) -> None:
    """A session that exists only as a line of the list, entered like one by hand. Its duration
    is in whole minutes, as every entry by hand is."""
    if row.elapsed_seconds is None:
        raise _Unusable
    minutes = round(row.elapsed_seconds / 60)
    if not 1 <= minutes <= DURATION_MAX_MINUTES or row.start.date() < EARLIEST:
        raise _Unusable
    kilometres = None if row.distance_m is None else row.distance_m / 1000
    if kilometres is not None and kilometres > DISTANCE_MAX_KM:
        kilometres = None
    enter_activity(
        user,
        sport=row.sport,
        start=row.start,
        duration_minutes=minutes,
        distance_km=kilometres,
    )
