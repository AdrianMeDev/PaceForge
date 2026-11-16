"""Which threshold value counts, and how a user sets or clears their own.

A threshold can be held by several sources at once (see ``ThresholdValue``). The order is fixed:
a value the user typed in, then one read from Intervals.icu, then an estimate from activities.
Every function acts on the values of the user it is given and on nothing else.
"""

import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from django.core.exceptions import ValidationError
from django.db import transaction

from accounts.models import User

from . import best_times
from .models import ThresholdValue

Metric = ThresholdValue.Metric
Source = ThresholdValue.Source

# A threshold pace that follows from a recent best time. It is not stored as a row of
# ``ThresholdValue``: it is worked out when the candidates are read (see ``best_times``).
BEST_TIME = "best_time"
PACE = ("run", Metric.THRESHOLD_PACE)

# The first source that holds a value wins.
PRIORITY = (Source.MANUAL, BEST_TIME, Source.INTERVALS, Source.ESTIMATED)


@dataclass(frozen=True)
class Value:
    value: float
    source: str
    basis: str
    updated_at: datetime


def _sorted(values: Iterable[Value]) -> list[Value]:
    return sorted(values, key=lambda candidate: PRIORITY.index(candidate.source))


def _best_time_value(user: User) -> Value | None:
    """The threshold pace of the best time that counts, if there is one."""
    entry = best_times.counting(best_times.entries(user))
    if entry is None:
        return None
    pace = best_times.pace_of(entry)
    if pace is None:
        return None
    return Value(pace, BEST_TIME, best_times.basis_of(entry), entry.updated_at)


def candidates(user: User, sport: str, metric: str) -> list[Value]:
    """Every value the user has for this threshold, the one that counts first."""
    values = [
        Value(row.value, row.source, row.basis, row.updated_at)
        for row in ThresholdValue.objects.for_user(user).filter(sport=sport, metric=metric)
    ]
    if (sport, metric) == PACE and (from_race := _best_time_value(user)) is not None:
        values.append(from_race)
    return _sorted(values)


def all_candidates(user: User) -> dict[tuple[str, str], list[Value]]:
    """The candidates of every threshold the user has a value for, with two queries."""
    grouped: dict[tuple[str, str], list[Value]] = {}
    for row in ThresholdValue.objects.for_user(user):
        grouped.setdefault((row.sport, row.metric), []).append(
            Value(row.value, row.source, row.basis, row.updated_at)
        )
    if (from_race := _best_time_value(user)) is not None:
        grouped.setdefault(PACE, []).append(from_race)
    return {key: _sorted(values) for key, values in grouped.items()}


def effective(user: User, sport: str, metric: str) -> Value | None:
    found = candidates(user, sport, metric)
    return found[0] if found else None


def set_manual(user: User, sport: str, metric: str, value: float) -> ThresholdValue:
    """Store the value the user typed in, replacing an earlier one of theirs.

    The value is checked like any other (sport and metric must fit, the range, a real number) and
    rounded to a whole number. Values from other sources stay as they are. Raises
    ``ValidationError`` and stores nothing if the value is refused.
    """
    whole = whole_number(user, sport, metric, Source.MANUAL, value)
    _check_against_the_other_heart_rate(user, sport, metric, whole)

    with transaction.atomic():
        stored, _ = ThresholdValue.objects.update_or_create(
            owner=user,
            sport=sport,
            metric=metric,
            source=Source.MANUAL,
            defaults={"value": whole, "basis": ""},
        )
    return stored


def whole_number(user: User, sport: str, metric: str, source: str, value: float) -> float:
    """``value`` as a whole number, after the checks every threshold goes through (sport and
    metric must fit, the range, a real number). Raises ``ValidationError``."""
    candidate = ThresholdValue(owner=user, sport=sport, metric=metric, source=source, value=value)
    # The unique constraint is what lets a value replace the earlier one: do not check it here.
    candidate.full_clean(
        exclude=["owner", "basis"], validate_unique=False, validate_constraints=False
    )
    return float(math.floor(candidate.value + 0.5))


def clear_manual(user: User, sport: str, metric: str) -> bool:
    """Remove the value the user typed in, so the next source counts again. ``False`` if there
    was none."""
    deleted, _ = (
        ThresholdValue.objects.for_user(user)
        .filter(sport=sport, metric=metric, source=Source.MANUAL)
        .delete()
    )
    return deleted > 0


def _check_against_the_other_heart_rate(user: User, sport: str, metric: str, value: float) -> None:
    """The lactate threshold heart rate cannot be above the maximum heart rate of the same sport.

    Compared with what the user typed in or Intervals.icu holds. An estimate never blocks an entry:
    if it is wrong, the user must still be able to enter the right value.
    """
    if metric not in (Metric.LTHR, Metric.MAX_HR):
        return
    other_metric = Metric.MAX_HR if metric == Metric.LTHR else Metric.LTHR
    other = effective(user, sport, other_metric)
    if other is None or other.source == Source.ESTIMATED:
        return
    if metric == Metric.LTHR and value > other.value:
        message = f"Cannot be above the maximum heart rate ({other.value:g} bpm)."
    elif metric == Metric.MAX_HR and value < other.value:
        message = f"Cannot be below the lactate threshold heart rate ({other.value:g} bpm)."
    else:
        return
    raise ValidationError({"value": message})
