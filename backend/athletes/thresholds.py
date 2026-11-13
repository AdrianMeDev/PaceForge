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

from .models import ThresholdValue

Metric = ThresholdValue.Metric
Source = ThresholdValue.Source

# The first source that holds a value wins.
PRIORITY = (Source.MANUAL, Source.INTERVALS, Source.ESTIMATED)


@dataclass(frozen=True)
class Value:
    value: float
    source: str
    basis: str
    updated_at: datetime


def _in_order(rows: Iterable[ThresholdValue]) -> list[Value]:
    values = [Value(row.value, row.source, row.basis, row.updated_at) for row in rows]
    return sorted(values, key=lambda candidate: PRIORITY.index(candidate.source))


def candidates(user: User, sport: str, metric: str) -> list[Value]:
    """Every value the user has for this threshold, the one that counts first."""
    return _in_order(ThresholdValue.objects.for_user(user).filter(sport=sport, metric=metric))


def all_candidates(user: User) -> dict[tuple[str, str], list[Value]]:
    """The candidates of every threshold the user has a value for, with one query."""
    grouped: dict[tuple[str, str], list[ThresholdValue]] = {}
    for row in ThresholdValue.objects.for_user(user):
        grouped.setdefault((row.sport, row.metric), []).append(row)
    return {key: _in_order(rows) for key, rows in grouped.items()}


def effective(user: User, sport: str, metric: str) -> Value | None:
    found = candidates(user, sport, metric)
    return found[0] if found else None


def set_manual(user: User, sport: str, metric: str, value: float) -> ThresholdValue:
    """Store the value the user typed in, replacing an earlier one of theirs.

    The value is checked like any other (sport and metric must fit, the range, a real number) and
    rounded to a whole number. Values from other sources stay as they are. Raises
    ``ValidationError`` and stores nothing if the value is refused.
    """
    candidate = ThresholdValue(
        owner=user, sport=sport, metric=metric, source=Source.MANUAL, value=value
    )
    # The unique constraint is what lets a second value replace the first: do not check it here.
    candidate.full_clean(
        exclude=["owner", "basis"], validate_unique=False, validate_constraints=False
    )
    whole = math.floor(candidate.value + 0.5)
    _check_against_the_other_heart_rate(user, sport, metric, whole)

    with transaction.atomic():
        stored, _ = ThresholdValue.objects.update_or_create(
            owner=user,
            sport=sport,
            metric=metric,
            source=Source.MANUAL,
            defaults={"value": float(whole), "basis": ""},
        )
    return stored


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
