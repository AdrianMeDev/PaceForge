"""Reads the summary of an activity from a FIT file.

The file is untrusted input: the CRC is verified, the number of messages and laps is capped, and
every failure of the library becomes an ``InvalidFileError`` with a fixed text. Only the first
frames of interest are kept while reading; the values are extracted afterwards.
"""

import io
from typing import Any

import fitdecode

from . import values
from .types import (
    CYCLING,
    FIT_FILE,
    MAX_LAPS,
    OTHER,
    RUNNING,
    STRENGTH,
    SWIMMING,
    ActivityFileError,
    InvalidFileError,
    ParsedActivity,
    ParsedLap,
    UnsupportedFileError,
)

# About 70 hours at one record per second. The library reads 15 000 (rich records) to 65 000
# (simple records) messages per second, so this bounds the time one upload can take to seconds.
MAX_MESSAGES = 250_000

_SPORTS = {"running": RUNNING, "cycling": CYCLING, "e_biking": CYCLING, "swimming": SWIMMING}


def parse_fit(data: bytes) -> ParsedActivity:
    if len(data) < 12 or data[8:12] != b".FIT":
        raise UnsupportedFileError("This is not a FIT file.")

    headers = messages = 0
    file_id = session = first_record = None
    laps: list[Any] = []
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
                    if frame.name == "file_id" and file_id is None:
                        file_id = frame
                    elif frame.name == "session":
                        if session is not None:
                            raise UnsupportedFileError(
                                "The file contains several sessions (for example a triathlon)."
                            )
                        session = frame
                    elif frame.name == "lap":
                        if len(laps) >= MAX_LAPS:
                            raise InvalidFileError("The file contains too many laps.")
                        laps.append(frame)
                    elif frame.name == "record" and first_record is None:
                        first_record = frame
    except ActivityFileError:
        raise
    except Exception:  # the library, on damaged or hostile input: whatever it raises
        raise InvalidFileError("The FIT file is damaged or incomplete.") from None

    if headers == 0 or file_id is None:
        raise InvalidFileError("The FIT file is damaged or incomplete.")
    if file_id.get_value("type", fallback=None) != "activity":
        raise UnsupportedFileError("This FIT file is not an activity.")
    if session is None:
        raise UnsupportedFileError("The FIT file contains no activity summary.")

    parsed_laps = tuple(_lap(frame) for frame in laps)
    start = (
        values.moment(session.get_value("start_time", fallback=None))
        or (
            values.moment(first_record.get_value("timestamp", fallback=None))
            if first_record
            else None
        )
        or next((lap.start_time for lap in parsed_laps if lap.start_time), None)
    )
    if start is None:
        raise InvalidFileError("The FIT file has no start time.")

    sport, source_sport = _sport(
        session.get_value("sport", fallback=None), session.get_value("sub_sport", fallback=None)
    )
    return ParsedActivity(
        source=FIT_FILE,
        sport=sport,
        source_sport=source_sport,
        start_time=start,
        elapsed_seconds=values.seconds(session.get_value("total_elapsed_time", fallback=None)),
        timer_seconds=values.seconds(session.get_value("total_timer_time", fallback=None)),
        distance_m=values.metres(session.get_value("total_distance", fallback=None)),
        avg_heart_rate=values.heart_rate(session.get_value("avg_heart_rate", fallback=None)),
        max_heart_rate=values.heart_rate(session.get_value("max_heart_rate", fallback=None)),
        avg_power_w=values.power(session.get_value("avg_power", fallback=None)),
        total_ascent_m=values.ascent(session.get_value("total_ascent", fallback=None)),
        calories=values.calories(session.get_value("total_calories", fallback=None)),
        manufacturer=values.text(file_id.get_value("manufacturer", fallback=None)),
        laps=parsed_laps,
    )


def _lap(frame: Any) -> ParsedLap:
    return ParsedLap(
        start_time=values.moment(frame.get_value("start_time", fallback=None)),
        elapsed_seconds=values.seconds(frame.get_value("total_elapsed_time", fallback=None)),
        distance_m=values.metres(frame.get_value("total_distance", fallback=None)),
        avg_heart_rate=values.heart_rate(frame.get_value("avg_heart_rate", fallback=None)),
        max_heart_rate=values.heart_rate(frame.get_value("max_heart_rate", fallback=None)),
    )


def _sport(sport: Any, sub_sport: Any) -> tuple[str, str]:
    """The normalised sport and the file's own wording (for what falls back to ``other``)."""
    name = sport if isinstance(sport, str) else (str(sport) if sport is not None else "")
    sub = sub_sport if isinstance(sub_sport, str) else ""
    raw = f"{name}/{sub}" if sub and sub != "generic" else name
    if sub == "strength_training":
        return STRENGTH, raw[:50]
    return _SPORTS.get(name, OTHER), raw[:50]
