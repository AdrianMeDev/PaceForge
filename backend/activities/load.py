"""The unified load of a session, from Intervals.icu or duration × RPE.

Intervals.icu activities carry a platform ``training_load``. For other activities (or Intervals
activities without ``training_load``), load is estimated from duration and RPE scaled by
``RPE_LOAD_PER_HOUR`` (10 per hour per RPE point) so both sit on one comparable scale. An activity
without ``training_load`` and without both duration and RPE has no load: nothing is guessed.
"""

import math
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal

from accounts.models import User
from goals.services import time_zone_of

from .duplicates import duration_of
from .models import Activity

RPE_LOAD_PER_HOUR = 10

LoadSource = Literal["intervals", "rpe"]


def _round_half_up(value: float) -> int:
    return math.floor(value + 0.5)


def rpe_load(seconds: float | None, rpe: int | None) -> int | None:
    """Whole load units, rounded half up; ``None`` if the duration or the RPE is not known."""
    if seconds is None or rpe is None:
        return None
    return _round_half_up(seconds / 3600 * rpe * RPE_LOAD_PER_HOUR)


def load_of(activity: Activity) -> int | None:
    """Rounded Intervals ``training_load`` when present, ``rpe_load`` otherwise, or ``None``."""
    if activity.training_load is not None:
        return _round_half_up(activity.training_load)
    return rpe_load(duration_of(activity.timer_seconds, activity.elapsed_seconds), activity.rpe)


def load_source_of(activity: Activity) -> LoadSource | None:
    """Where ``load_of`` comes from: ``"intervals"``, ``"rpe"``, or ``None``."""
    if activity.training_load is not None:
        return "intervals"
    seconds = duration_of(activity.timer_seconds, activity.elapsed_seconds)
    if rpe_load(seconds, activity.rpe) is not None:
        return "rpe"
    return None


def done_load_for_week(user: User, monday: date) -> int:
    """Total done load for ``user`` in the local week starting on ``monday``."""
    if monday.weekday() != 0:
        raise ValueError("A week starts on a Monday.")
    zone = time_zone_of(user)
    since = datetime.combine(monday, time.min, tzinfo=zone).astimezone(UTC)
    until = datetime.combine(monday + timedelta(days=7), time.min, tzinfo=zone).astimezone(UTC)
    activities = (
        Activity.objects.for_user(user)
        .filter(start_time__gte=since, start_time__lt=until)
        .only("training_load", "timer_seconds", "elapsed_seconds", "rpe")
    )
    return sum(load for activity in activities if (load := load_of(activity)) is not None)
