"""The best times of a user, the one that counts and the threshold pace that follows from it.

A best time counts if the race was in the last ``WINDOW_DAYS`` days; of those the newest counts, on
the same day the one with the higher VDOT. Older ones stay stored and shown but do not count. What
counts is worked out when it is read, so it needs no clean-up when a time gets too old.
"""

import math
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from accounts.models import User

from .models import BestTime
from .vdot import DISTANCES, VDOT_MAX, VDOT_MIN, threshold_pace, vdot

WINDOW_DAYS = 365
# What a threshold pace can be, as in ``models.RULES`` (seconds per kilometre).
PACE_MIN, PACE_MAX = 120, 1200


@dataclass(frozen=True)
class Entry:
    distance: str
    seconds: int
    date: date
    vdot: float
    # The race lies inside the window, so this time can count.
    recent: bool
    updated_at: datetime


def _today() -> date:
    """The day it is. A function of its own so that the tests can set it."""
    return datetime.now(UTC).date()


def entries(user: User) -> list[Entry]:
    """The stored best times of ``user`` in the order of ``DISTANCES``, each with its VDOT. A time
    whose VDOT is out of range (it cannot be entered, but the database may hold it) is left out.
    One query."""
    earliest = _today() - timedelta(days=WINDOW_DAYS)
    rows = {row.distance: row for row in BestTime.objects.for_user(user)}
    found = []
    for distance in DISTANCES:
        row = rows.get(distance)
        if row is None:
            continue
        value = vdot(DISTANCES[distance], row.seconds)
        if value is None or not VDOT_MIN <= value <= VDOT_MAX:
            continue
        found.append(
            Entry(distance, row.seconds, row.date, value, row.date >= earliest, row.updated_at)
        )
    return found


def counting(found: list[Entry]) -> Entry | None:
    """The best time that counts: the newest of the recent ones, the higher VDOT on the same day."""
    recent = [entry for entry in found if entry.recent]
    return max(recent, key=lambda entry: (entry.date, entry.vdot), default=None)


def pace_of(entry: Entry) -> float | None:
    """The threshold pace of a best time in whole seconds per kilometre (rounded half up, like every
    threshold); ``None`` if it is not a pace a threshold can have."""
    pace = threshold_pace(entry.vdot)
    if pace is None:
        return None
    whole = float(math.floor(pace + 0.5))
    return whole if PACE_MIN <= whole <= PACE_MAX else None


def basis_of(entry: Entry) -> str:
    """A short fixed text saying how the pace came about; nothing personal but the race day."""
    label = BestTime.Distance(entry.distance).label
    return f"VDOT {entry.vdot:.1f} from your {label} on {entry.date.isoformat()}"
