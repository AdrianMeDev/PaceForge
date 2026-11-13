"""Thresholds estimated from the activities a user imported.

Only rows with the source ``estimated`` are written, and only for the maximum heart rate: a value
the user typed in, or one read from Intervals.icu, always counts before an estimate.
"""

import logging
import math
from collections.abc import Iterable

from django.db import transaction

from accounts.models import User
from activities.models import Activity

from .models import RULES, ThresholdValue

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


def refresh_estimates(user: User) -> None:
    """Recompute the estimated maximum heart rate of the user, for running and for cycling.

    An estimate that no longer holds (an activity was deleted) is removed; an unchanged one is
    left as it is, so the time of its last change stays.
    """
    maxima: dict[str, list[int]] = {group: [] for group in GROUPS.values()}
    rows = (
        Activity.objects.for_user(user)
        .filter(sport__in=GROUPS, max_heart_rate__isnull=False)
        .values_list("sport", "max_heart_rate")
    )
    for sport, heart_rate in rows:
        if heart_rate is not None:  # the filter above, for the type checker
            maxima[GROUPS[sport]].append(heart_rate)

    with transaction.atomic():
        stored = {
            row.sport: row
            for row in ThresholdValue.objects.for_user(user).filter(
                metric=ThresholdValue.Metric.MAX_HR, source=ThresholdValue.Source.ESTIMATED
            )
        }
        for group, heart_rates in maxima.items():
            allowed = RULES[(group, ThresholdValue.Metric.MAX_HR)]
            estimate = estimate_max_heart_rate(
                heart_rates, minimum=allowed.minimum, maximum=allowed.maximum
            )
            current = stored.get(group)
            if estimate is None:
                if current is not None:
                    current.delete()
            elif current is None or current.value != estimate or current.basis != BASIS:
                ThresholdValue.objects.update_or_create(
                    owner=user,
                    sport=group,
                    metric=ThresholdValue.Metric.MAX_HR,
                    source=ThresholdValue.Source.ESTIMATED,
                    defaults={"value": float(estimate), "basis": BASIS},
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
