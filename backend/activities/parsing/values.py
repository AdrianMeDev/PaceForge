"""Plausibility checks for values read from files.

A value outside what a person can do or a device can measure is dropped (``None``), not clamped
and not guessed: the activity is still imported, just without that number.
"""

import math
from datetime import UTC, datetime
from typing import Any

MAX_SECONDS = 30 * 24 * 3600.0
MAX_DISTANCE_M = 10_000_000.0
MAX_HEART_RATE = 300
MAX_POWER_W = 5000
MAX_ASCENT_M = 20_000
MAX_CALORIES = 100_000


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value) if math.isfinite(value) else None


def seconds(value: Any) -> float | None:
    number = _number(value)
    return number if number is not None and 0 <= number <= MAX_SECONDS else None


def metres(value: Any) -> float | None:
    number = _number(value)
    return number if number is not None and 0 <= number <= MAX_DISTANCE_M else None


def whole(value: Any, *, minimum: int, maximum: int) -> int | None:
    number = _number(value)
    if number is None or not minimum <= number <= maximum:
        return None
    return round(number)


def heart_rate(value: Any) -> int | None:
    return whole(value, minimum=1, maximum=MAX_HEART_RATE)  # 0 bpm is no measurement


def power(value: Any) -> int | None:
    return whole(value, minimum=0, maximum=MAX_POWER_W)


def ascent(value: Any) -> int | None:
    return whole(value, minimum=0, maximum=MAX_ASCENT_M)


def calories(value: Any) -> int | None:
    return whole(value, minimum=0, maximum=MAX_CALORIES)


def moment(value: Any) -> datetime | None:
    """A point in time as an aware UTC datetime; anything else is ``None``."""
    if not isinstance(value, datetime):
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def text(value: Any, *, limit: int = 50) -> str:
    return value[:limit] if isinstance(value, str) else ""
