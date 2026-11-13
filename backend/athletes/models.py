import math
from dataclasses import dataclass
from functools import cache
from typing import Any
from zoneinfo import available_timezones

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from core.models import OwnedModel


@cache
def _time_zones() -> frozenset[str]:
    # "Factory" is a placeholder zone of the time zone database, not a place anyone lives in.
    return frozenset(available_timezones() - {"Factory"})


def validate_time_zone(value: str) -> None:
    """Accept only names of the IANA time zone database, spelled exactly (``Europe/Berlin``).

    A set lookup instead of ``ZoneInfo(value)``: the latter treats the name as a file path.
    """
    if value not in _time_zones():
        raise ValidationError(
            "Enter a time zone from the IANA database, for example Europe/Berlin."
        )


class AthleteProfile(OwnedModel):
    """What PaceForge knows about a user as an athlete. One per user, created on first use.

    The thresholds live in ``ThresholdValue``, one row per value and source.
    """

    # Empty: not set yet. The name is validated, never used as a path.
    timezone = models.CharField(max_length=64, blank=True, validators=[validate_time_zone])
    # When the thresholds were last read from Intervals.icu; empty: never.
    intervals_synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["owner"], name="athletes_one_profile_per_owner"),
        ]

    def __str__(self) -> str:
        return f"Athlete profile of user {self.owner_id}"


@dataclass(frozen=True)
class ValueRange:
    minimum: float
    maximum: float
    unit: str


class ThresholdValue(OwnedModel):
    """One candidate for a threshold: a value together with where it came from.

    The same threshold can be held by several sources at once (typed in, read from Intervals.icu,
    estimated from activities); which one counts is decided where the values are used, not here.
    Units: watts for ``ftp``, beats per minute for ``lthr`` and ``max_hr``, seconds per kilometre
    for ``threshold_pace``.
    """

    class Sport(models.TextChoices):
        RIDE = "ride", "Cycling"
        RUN = "run", "Running"

    class Metric(models.TextChoices):
        FTP = "ftp", "FTP"
        LTHR = "lthr", "Lactate threshold heart rate"
        MAX_HR = "max_hr", "Maximum heart rate"
        THRESHOLD_PACE = "threshold_pace", "Threshold pace"

    class Source(models.TextChoices):
        MANUAL = "manual", "Entered by the user"
        INTERVALS = "intervals", "Intervals.icu"
        ESTIMATED = "estimated", "Estimated from activities"

    sport = models.CharField(max_length=10, choices=Sport.choices)
    metric = models.CharField(max_length=20, choices=Metric.choices)
    value = models.FloatField()
    source = models.CharField(max_length=20, choices=Source.choices)
    # A short fixed text saying how the value came about; never anything personal.
    basis = models.CharField(max_length=200, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "sport", "metric", "source"],
                name="athletes_one_value_per_source",
            ),
            models.CheckConstraint(condition=Q(value__gt=0), name="athletes_value_positive"),
            # Cycling has power, running has pace; both have the heart rates.
            models.CheckConstraint(
                condition=(
                    Q(sport="ride", metric__in=["ftp", "lthr", "max_hr"])
                    | Q(sport="run", metric__in=["threshold_pace", "lthr", "max_hr"])
                ),
                name="athletes_metric_fits_sport",
            ),
        ]

    def __str__(self) -> str:
        # No value: it is personal data and has no business in logs and admin lists.
        return f"{self.sport} {self.metric} ({self.source}) of user {self.owner_id}"

    def clean(self) -> None:
        super().clean()
        if self.sport not in self.Sport.values or self.metric not in self.Metric.values:
            return  # the choices check of the fields reports that
        rule = RULES.get((self.sport, self.metric))
        if rule is None:
            raise ValidationError(
                {"metric": f"{self.get_metric_display()} does not apply to this sport."}
            )
        value: Any = self.value
        if not isinstance(value, int | float) or not math.isfinite(value):
            raise ValidationError({"value": "Enter a number."})
        if not rule.minimum <= value <= rule.maximum:
            span = f"{rule.minimum:g} and {rule.maximum:g} {rule.unit}"
            raise ValidationError({"value": f"Enter a value between {span}."})


# Which metric applies to which sport, and what a plausible value looks like.
RULES: dict[tuple[str, str], ValueRange] = {
    ("ride", "ftp"): ValueRange(30, 2000, "W"),
    ("ride", "lthr"): ValueRange(30, 250, "bpm"),
    ("ride", "max_hr"): ValueRange(30, 250, "bpm"),
    ("run", "threshold_pace"): ValueRange(120, 1200, "s/km"),
    ("run", "lthr"): ValueRange(30, 250, "bpm"),
    ("run", "max_hr"): ValueRange(30, 250, "bpm"),
}
