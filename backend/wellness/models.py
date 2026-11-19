"""Daily wellness metrics synced from Intervals.icu, one row per user and day.

Only the four metrics the Intervals client whitelists are stored (``intervals.IntervalsWellness``):
sleep, HRV, resting heart rate and weight. Every metric is optional on a day; a day has no row at
all before it has been read, and a day whose metrics are all missing is never stored. The ranges
match what a person can report and are enforced by the database; the values that reach the AI
coach are only these fixed numbers, never free text.
"""

import uuid

from django.db import models
from django.db.models import Q

from core.models import OwnedModel

# The plausible ranges of the four metrics (see integrations.intervals). Whole minutes of sleep
# from a minimum of one minute to a full day.
SLEEP_MINUTES_MIN, SLEEP_MINUTES_MAX = 1, 1440
# HRV is rMSSD in milliseconds.
HRV_MIN, HRV_MAX = 1, 300
RESTING_HR_MIN, RESTING_HR_MAX = 25, 120
WEIGHT_MIN, WEIGHT_MAX = 25, 300


def _nullable_in_range(field: str, low: int | float, high: int | float) -> Q:
    """A value that is either not given or between the ends (both included)."""
    return Q(**{f"{field}__isnull": True}) | Q(**{f"{field}__gte": low, f"{field}__lte": high})


class DailyWellness(OwnedModel):
    """One day of an athlete's sleep, HRV, resting heart rate and weight. One row per user and day.

    The day is the calendar day in the user's time zone, decided where the data is read and stored
    (the sync uses ``today_of``). ``updated_at`` is bumped whenever a synced value changes, so the
    id stays stable while Intervals.icu keeps updating the same day.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    day = models.DateField()
    sleep_minutes = models.PositiveSmallIntegerField(null=True, blank=True)
    hrv = models.FloatField(null=True, blank=True)
    resting_hr = models.PositiveSmallIntegerField(null=True, blank=True)
    weight_kg = models.FloatField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["day"]
        constraints = [
            models.UniqueConstraint(fields=["owner", "day"], name="wellness_one_per_user_and_day"),
            models.CheckConstraint(
                condition=_nullable_in_range("sleep_minutes", SLEEP_MINUTES_MIN, SLEEP_MINUTES_MAX),
                name="wellness_sleep_minutes_in_range",
            ),
            models.CheckConstraint(
                condition=_nullable_in_range("hrv", HRV_MIN, HRV_MAX),
                name="wellness_hrv_in_range",
            ),
            models.CheckConstraint(
                condition=_nullable_in_range("resting_hr", RESTING_HR_MIN, RESTING_HR_MAX),
                name="wellness_resting_hr_in_range",
            ),
            models.CheckConstraint(
                condition=_nullable_in_range("weight_kg", WEIGHT_MIN, WEIGHT_MAX),
                name="wellness_weight_in_range",
            ),
        ]

    def __str__(self) -> str:
        return f"wellness of user {self.owner_id} on {self.day:%Y-%m-%d}"
