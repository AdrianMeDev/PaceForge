"""Thresholds estimated from the activities a user imported.

Only rows with the source ``estimated`` are written: a value the user typed in, or one read from
Intervals.icu, always counts before an estimate.
"""

import logging
import math
from collections.abc import Iterable
from datetime import timedelta
from typing import TypeGuard

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from accounts.models import User
from activities.models import Activity

from .models import RULES, ThresholdValue
from .thresholds import whole_number

logger = logging.getLogger(__name__)

BASIS = "Highest value reached in at least two activities"
MIN_ACTIVITIES = 3
# How close a second activity has to come for the highest value to be believed.
CONFIRMATION_BPM = 3
# The sport of an activity decides which sport group its heart rate counts for.
GROUPS: dict[str, str] = {Activity.Sport.RUNNING: "run", Activity.Sport.CYCLING: "ride"}


def estimate_max_heart_rate(
    values: Iterable[float], *, minimum: float, maximum: float
) -> int | None:
    """The maximum heart rate that the maxima of several activities agree on, or ``None``.

    Optical sensors produce single false peaks, so the highest value counts only if another
    activity came within ``CONFIRMATION_BPM`` below it; otherwise the next highest is tried. Values
    outside ``minimum`` to ``maximum`` are ignored, and fewer than ``MIN_ACTIVITIES`` usable
    values give no estimate at all.
    """
    usable = sorted((v for v in values if minimum <= v <= maximum), reverse=True)
    if len(usable) < MIN_ACTIVITIES:
        return None
    for higher, lower in zip(usable, usable[1:], strict=False):
        if higher - lower <= CONFIRMATION_BPM:
            return math.floor(higher + 0.5)
    return None


# Only recent activities say something about today's thresholds.
RECENT_DAYS = 90
# Field-test conventions (Joe Friel; Andrew Coggan for the FTP). Training rarely holds an all-out
# effort, so each estimate is a lower bound, and the basis says so.
FTP_SHARE = 0.95  # of the best 20-minute power
RIDE_LTHR_SHARE = 0.95  # of the heart rate during that effort
POWER_WINDOW = "1200"
PACE_WINDOW = "1800"
FTP_BASIS = "At least 95 % of your best 20-minute power in the last 90 days"
RIDE_LTHR_BASIS = (
    "At least 95 % of your heart rate during your best 20-minute power in the last 90 days"
)
PACE_BASIS = "At least as fast as your best 30-minute pace in the last 90 days"
RUN_LTHR_BASIS = "At least your heart rate during your best 30-minute pace in the last 90 days"

Wanted = dict[tuple[str, str], tuple[float, str]]


def refresh_estimates(user: User) -> None:
    """Recompute the user's estimated thresholds, for running and for cycling: the maximum heart
    rate from all activities, FTP, threshold pace and LTHR from the best efforts of the last
    ``RECENT_DAYS`` days.

    An estimate that no longer holds (an activity was deleted, or it became too old) is removed;
    an unchanged one is left as it is, so the time of its last change stays. Each value goes
    through the same checks as a typed one; a value outside them is not stored.
    """
    wanted = _maximum_heart_rates(user) | _from_best_efforts(user)
    for (sport, metric), (value, basis) in list(wanted.items()):
        try:
            wanted[(sport, metric)] = (
                whole_number(user, sport, metric, ThresholdValue.Source.ESTIMATED, value),
                basis,
            )
        except ValidationError:
            del wanted[(sport, metric)]

    with transaction.atomic():
        stored = {
            (row.sport, row.metric): row
            for row in ThresholdValue.objects.for_user(user).filter(
                source=ThresholdValue.Source.ESTIMATED
            )
        }
        for key, row in stored.items():
            if key not in wanted:
                row.delete()
        for (sport, metric), (value, basis) in wanted.items():
            current = stored.get((sport, metric))
            if current is not None and current.value == value and current.basis == basis:
                continue
            ThresholdValue.objects.update_or_create(
                owner=user,
                sport=sport,
                metric=metric,
                source=ThresholdValue.Source.ESTIMATED,
                defaults={"value": value, "basis": basis},
            )


def _maximum_heart_rates(user: User) -> Wanted:
    maxima: dict[str, list[int]] = {group: [] for group in GROUPS.values()}
    rows = (
        Activity.objects.for_user(user)
        .filter(sport__in=GROUPS, max_heart_rate__isnull=False)
        .values_list("sport", "max_heart_rate")
    )
    for sport, heart_rate in rows:
        if heart_rate is not None:  # the filter above, for the type checker
            maxima[GROUPS[sport]].append(heart_rate)

    wanted: Wanted = {}
    for group, heart_rates in maxima.items():
        allowed = RULES[(group, ThresholdValue.Metric.MAX_HR)]
        estimate = estimate_max_heart_rate(
            heart_rates, minimum=allowed.minimum, maximum=allowed.maximum
        )
        if estimate is not None:
            wanted[(group, ThresholdValue.Metric.MAX_HR)] = (float(estimate), BASIS)
    return wanted


def _from_best_efforts(user: User) -> Wanted:
    """FTP and LTHR from the best 20-minute power of the recent rides; threshold pace and LTHR
    from the best 30-minute speed of the recent runs."""
    since = timezone.now() - timedelta(days=RECENT_DAYS)
    best: dict[str, tuple[float, float | None]] = {}  # group -> (value, heart rate)
    rows = (
        Activity.objects.for_user(user)
        .filter(sport__in=GROUPS, start_time__gte=since, best_efforts__isnull=False)
        .values_list("sport", "best_efforts")
    )
    for sport, efforts in rows:
        group = GROUPS[sport]
        kind, window = ("power", POWER_WINDOW) if group == "ride" else ("speed", PACE_WINDOW)
        effort = _effort(efforts, kind, window)
        if effort is not None and (group not in best or effort[0] > best[group][0]):
            best[group] = effort

    wanted: Wanted = {}
    if "ride" in best:
        power, heart_rate = best["ride"]
        wanted[("ride", "ftp")] = (power * FTP_SHARE, FTP_BASIS)
        if heart_rate is not None:
            wanted[("ride", "lthr")] = (heart_rate * RIDE_LTHR_SHARE, RIDE_LTHR_BASIS)
    if "run" in best:
        speed, heart_rate = best["run"]
        wanted[("run", "threshold_pace")] = (1000 / speed, PACE_BASIS)
        if heart_rate is not None:
            wanted[("run", "lthr")] = (heart_rate, RUN_LTHR_BASIS)
    return wanted


def _effort(efforts: object, kind: str, window: str) -> tuple[float, float | None] | None:
    """One stored effort as (value, heart rate); anything of the wrong shape counts as none."""
    part = efforts.get(kind) if isinstance(efforts, dict) else None
    entry = part.get(window) if isinstance(part, dict) else None
    if not isinstance(entry, dict):
        return None
    value, heart_rate = entry.get("value"), entry.get("heart_rate")
    if not _positive(value):
        return None
    return float(value), float(heart_rate) if _positive(heart_rate) else None


def _positive(value: object) -> TypeGuard[float]:
    return (
        isinstance(value, int | float)
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value > 0
    )


def refresh_estimates_safely(user: User) -> None:
    """``refresh_estimates`` for callers that must not fail because of it (an import).

    A failure is logged and the estimates stay as they were; the next import or deletion tries
    again.
    """
    try:
        refresh_estimates(user)
    except Exception:
        logger.exception("Could not refresh the estimated thresholds of user %s", user.pk)
