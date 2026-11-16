import math
from dataclasses import dataclass
from datetime import date
from functools import cache
from importlib import resources
from typing import Any

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from core.models import OwnedModel

from .vdot import DISTANCES, VDOT_MAX, VDOT_MIN, vdot

# The earliest date of a best time.
BEST_TIME_FROM = date(1900, 1, 1)

# What is plausible for the body and training data of an athlete (US-3.1).
BIRTH_YEAR_MIN = 1900
# The youngest athlete: the birth year cannot be later than this many years ago.
MIN_AGE = 10
WEIGHT_MIN, WEIGHT_MAX = 25, 300
RESTING_HR_MIN, RESTING_HR_MAX = 25, 120
TRAINING_YEARS_MAX = 80


@cache
def _time_zones() -> frozenset[str]:
    """The zone names of the ``tzdata`` package, the same on every host.

    Not ``zoneinfo.available_timezones()``: that reads the operating system's directory, which on
    some systems also holds names that are no places (``localtime``, ``posixrules``, the
    ``posix/`` and ``right/`` copies). "Factory" is a placeholder of the database itself.
    """
    names = resources.files("tzdata").joinpath("zones").read_text().split()
    return frozenset(names) - {"Factory"}


def validate_time_zone(value: str) -> None:
    """Accept only names of the IANA time zone database, spelled exactly (``Europe/Berlin``).

    A set lookup instead of ``ZoneInfo(value)``: the latter treats the name as a file path.
    """
    if value not in _time_zones():
        raise ValidationError(
            "Enter a time zone from the IANA database, for example Europe/Berlin."
        )


# The sports that have a number of years of training.
YEARS_SPORTS = ("running", "cycling", "swimming", "strength")


class Sex(models.TextChoices):
    FEMALE = "female", "Female"
    MALE = "male", "Male"
    OTHER = "other", "Other"


class StrengthExperience(models.TextChoices):
    BEGINNER = "beginner", "Beginner"
    ADVANCED = "advanced", "Advanced"


class Equipment(models.TextChoices):
    """What an athlete has for strength training, in the order it is listed and stored."""

    GYM = "gym", "Gym"
    HOME = "home", "At home"
    DUMBBELLS = "dumbbells", "Dumbbells"


def _in_range(field: str, low: int, high: int) -> Q:
    """A number that is either not given or between the ends (both included)."""
    return Q(**{f"{field}__isnull": True}) | Q(**{f"{field}__gte": low, f"{field}__lte": high})


class AthleteProfile(OwnedModel):
    """What PaceForge knows about a user as an athlete. One per user, created on first use.

    The thresholds live in ``ThresholdValue``, one row per value and source.
    """

    # Empty: not set yet. The name is validated, never used as a path.
    timezone = models.CharField(max_length=64, blank=True, validators=[validate_time_zone])
    # When the thresholds were last read from Intervals.icu; empty: never.
    intervals_synced_at = models.DateTimeField(null=True, blank=True)

    # Body and training data, all optional. They go to the AI coach as numbers and fixed words, so
    # there is no free text here. An empty text or list (and ``None``) means "not said"; the API
    # says ``null``.
    birth_year = models.PositiveSmallIntegerField(null=True, blank=True)
    sex = models.CharField(max_length=10, choices=Sex.choices, blank=True, default="")
    weight_kg = models.FloatField(null=True, blank=True)
    resting_hr = models.PositiveSmallIntegerField(null=True, blank=True)
    # Whole years of training in each sport.
    years_running = models.PositiveSmallIntegerField(null=True, blank=True)
    years_cycling = models.PositiveSmallIntegerField(null=True, blank=True)
    years_swimming = models.PositiveSmallIntegerField(null=True, blank=True)
    years_strength = models.PositiveSmallIntegerField(null=True, blank=True)
    strength_experience = models.CharField(
        max_length=10, choices=StrengthExperience.choices, blank=True, default=""
    )
    strength_equipment = models.JSONField(default=list, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["owner"], name="athletes_one_profile_per_owner"),
            models.CheckConstraint(
                condition=Q(birth_year__isnull=True) | Q(birth_year__gte=BIRTH_YEAR_MIN),
                name="athletes_birth_year_plausible",
            ),
            models.CheckConstraint(
                condition=Q(sex__in=["", *Sex.values]), name="athletes_sex_known"
            ),
            models.CheckConstraint(
                condition=_in_range("weight_kg", WEIGHT_MIN, WEIGHT_MAX),
                name="athletes_weight_in_range",
            ),
            models.CheckConstraint(
                condition=_in_range("resting_hr", RESTING_HR_MIN, RESTING_HR_MAX),
                name="athletes_resting_hr_in_range",
            ),
            *(
                models.CheckConstraint(
                    condition=_in_range(f"years_{sport}", 0, TRAINING_YEARS_MAX),
                    name=f"athletes_years_{sport}_in_range",
                )
                for sport in YEARS_SPORTS
            ),
            models.CheckConstraint(
                condition=Q(strength_experience__in=["", *StrengthExperience.values]),
                name="athletes_strength_experience_known",
            ),
        ]

    def __str__(self) -> str:
        return f"Athlete profile of user {self.owner_id}"

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        latest = date.today().year - MIN_AGE
        if self.birth_year is not None and not BIRTH_YEAR_MIN <= self.birth_year <= latest:
            errors["birth_year"] = f"Enter a year between {BIRTH_YEAR_MIN} and {latest}."
        weight: Any = self.weight_kg
        if weight is not None and not (
            isinstance(weight, int | float)
            and not isinstance(weight, bool)
            and math.isfinite(weight)
            and WEIGHT_MIN <= weight <= WEIGHT_MAX
        ):
            errors["weight_kg"] = f"Enter a weight between {WEIGHT_MIN} and {WEIGHT_MAX} kg."
        resting = self.resting_hr
        if resting is not None and not RESTING_HR_MIN <= resting <= RESTING_HR_MAX:
            errors["resting_hr"] = (
                f"Enter a resting heart rate between {RESTING_HR_MIN} and {RESTING_HR_MAX} bpm."
            )
        for sport in YEARS_SPORTS:
            years = getattr(self, f"years_{sport}")
            if years is not None and not 0 <= years <= TRAINING_YEARS_MAX:
                errors[f"years_{sport}"] = f"Enter between 0 and {TRAINING_YEARS_MAX} years."
        equipment = self.strength_equipment
        if not (
            isinstance(equipment, list)
            and all(isinstance(item, str) and item in Equipment.values for item in equipment)
            and len(set(equipment)) == len(equipment)
        ):
            errors["strength_equipment"] = "Use each of gym, home and dumbbells at most once."
        if errors:
            raise ValidationError(errors)

    @property
    def equipment(self) -> list[str]:
        """The equipment in the order of ``Equipment``; nothing if the stored value is unusable."""
        stored = self.strength_equipment
        if not isinstance(stored, list):
            return []
        return [item for item in Equipment.values if item in stored]


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


class BestTime(OwnedModel):
    """The best time of a user over one of the distances of ``DISTANCES``, and the day of the race.

    One per user and distance: a new time replaces the old one. The VDOT and the threshold pace
    that follow from it are computed where they are used (see ``athletes/best_times.py``), not
    stored.
    """

    class Distance(models.TextChoices):
        FIVE_K = "5k", "5 km"
        TEN_K = "10k", "10 km"
        HALF_MARATHON = "half_marathon", "Half marathon"
        MARATHON = "marathon", "Marathon"

    distance = models.CharField(max_length=20, choices=Distance.choices)
    # Whole seconds.
    seconds = models.PositiveIntegerField()
    date = models.DateField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "distance"], name="athletes_one_best_time_per_distance"
            ),
            models.CheckConstraint(
                condition=Q(distance__in=list(DISTANCES)), name="athletes_best_time_distance_known"
            ),
            models.CheckConstraint(
                condition=Q(seconds__gt=0), name="athletes_best_time_seconds_positive"
            ),
            models.CheckConstraint(
                condition=Q(date__gte=BEST_TIME_FROM), name="athletes_best_time_date_plausible"
            ),
        ]

    def __str__(self) -> str:
        # No time: it is personal data and has no business in logs and admin lists.
        return f"{self.distance} best time of user {self.owner_id}"

    def clean(self) -> None:
        super().clean()
        if self.distance not in DISTANCES:
            return  # the choices check of the fields reports that
        errors: dict[str, str] = {}
        if self.seconds is not None:
            found = vdot(DISTANCES[self.distance], self.seconds)
            if found is None or not VDOT_MIN <= found <= VDOT_MAX:
                errors["seconds"] = "That time is not plausible for this distance. Check it."
        day = self.date
        if day is not None and (day < BEST_TIME_FROM or day > date.today()):
            errors["date"] = "Enter the day of the race: not in the future, not before 1900."
        if errors:
            raise ValidationError(errors)
