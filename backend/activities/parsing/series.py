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
