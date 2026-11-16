import uuid
from typing import Any

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from athletes.models import RULES
from core.models import OwnedModel

TITLE_MAX = 100
NOTES_MAX = 1000
# From a minute (a sprint) to a hundred hours (the longest ultra), in seconds.
TARGET_TIME_MIN, TARGET_TIME_MAX = 60, 360_000
# The longest distance anyone enters, in metres (a thousand kilometres).
DISTANCE_MAX = 1_000_000

# The sport a threshold belongs to, for looking up its plausible range.
_SPORT_OF_METRIC = {"ftp": "ride", "threshold_pace": "run"}


class Goal(OwnedModel):
    """Something a user trains for: a race, a threshold to raise, or a general aim.

    Which fields apply depends on ``kind``; the others must stay empty. A user has at most one
    active main goal, the database enforces it.
    """

    class Kind(models.TextChoices):
        RACE = "race", "Race"
        THRESHOLD = "threshold", "Threshold"
        GENERAL = "general", "General"

    class Priority(models.TextChoices):
        MAIN = "main", "Main goal"
        SECONDARY = "secondary", "Secondary goal"
        # A race on the way to the main goal; only a race can be one.
        PREPARATION = "preparation", "Preparation race"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        ACHIEVED = "achieved", "Achieved"
        DROPPED = "dropped", "Dropped"

    class Discipline(models.TextChoices):
        RUNNING = "running", "Running"
        CYCLING = "cycling", "Cycling"
        SWIMMING = "swimming", "Swimming"
        TRIATHLON = "triathlon", "Triathlon"

    class Metric(models.TextChoices):
        FTP = "ftp", "FTP"
        THRESHOLD_PACE = "threshold_pace", "Threshold pace"

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    kind = models.CharField(max_length=20, choices=Kind.choices)
    title = models.CharField(max_length=TITLE_MAX)
    notes = models.CharField(max_length=NOTES_MAX, blank=True)
    priority = models.CharField(max_length=20, choices=Priority.choices, default=Priority.SECONDARY)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    # The day of the race, or the day by which a threshold should be reached. A calendar date:
    # which day "today" is depends on the user's time zone and is decided where it is used.
    target_date = models.DateField(null=True, blank=True)
    # Race only: the discipline, the distance in metres and the finishing time in seconds.
    discipline = models.CharField(max_length=20, choices=Discipline.choices, blank=True)
    distance_m = models.FloatField(null=True, blank=True)
    target_time_seconds = models.PositiveIntegerField(null=True, blank=True)
    # Threshold only: FTP in watts or the running threshold pace in seconds per kilometre.
    metric = models.CharField(max_length=20, choices=Metric.choices, blank=True)
    target_value = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["owner"],
                condition=Q(priority="main", status="active"),
                name="goals_one_active_main_goal",
            ),
            models.CheckConstraint(
                condition=~Q(kind="race") | (Q(target_date__isnull=False) & ~Q(discipline="")),
                name="goals_race_is_complete",
            ),
            models.CheckConstraint(
                condition=~Q(kind="threshold") | (~Q(metric="") & Q(target_value__isnull=False)),
                name="goals_threshold_is_complete",
            ),
            models.CheckConstraint(
                condition=~Q(priority="preparation") | Q(kind="race"),
                name="goals_preparation_is_a_race",
            ),
            models.CheckConstraint(condition=~Q(title=""), name="goals_title_not_empty"),
            models.CheckConstraint(
                condition=Q(distance_m__isnull=True)
                | (Q(distance_m__gt=0) & Q(distance_m__lte=DISTANCE_MAX)),
                name="goals_distance_in_range",
            ),
            models.CheckConstraint(
                condition=Q(target_time_seconds__isnull=True)
                | Q(
                    target_time_seconds__gte=TARGET_TIME_MIN,
                    target_time_seconds__lte=TARGET_TIME_MAX,
                ),
                name="goals_target_time_in_range",
            ),
            models.CheckConstraint(
                condition=Q(target_value__isnull=True) | Q(target_value__gt=0),
                name="goals_target_value_positive",
            ),
        ]

    def __str__(self) -> str:
        # No title: it is free text from the user and has no business in logs and admin lists.
        return f"{self.kind} goal of user {self.owner_id}"

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if not (self.title or "").strip():
            errors["title"] = "Enter a title."
        if self.priority == self.Priority.PREPARATION and self.kind != self.Kind.RACE:
            errors["priority"] = "Only a race can be a preparation race."
        if self.kind == self.Kind.RACE:
            self._clean_race(errors)
        elif self.kind == self.Kind.THRESHOLD:
            self._clean_threshold(errors)
        elif self.kind == self.Kind.GENERAL:
            self._must_be_empty(errors, ["discipline", "distance_m", "target_time_seconds"])
            self._must_be_empty(errors, ["metric", "target_value"])
        if errors:
            raise ValidationError(errors)

    def _clean_race(self, errors: dict[str, str]) -> None:
        if self.target_date is None:
            errors["target_date"] = "A race needs a date."
        if not self.discipline:
            errors["discipline"] = "A race needs a discipline."
        self._must_be_empty(errors, ["metric", "target_value"])
        if self.distance_m is not None and not _within(self.distance_m, 0, DISTANCE_MAX, True):
            errors["distance_m"] = "Enter a distance between 0 and 1000 km."
        time = self.target_time_seconds
        if time is not None and not TARGET_TIME_MIN <= time <= TARGET_TIME_MAX:
            errors["target_time_seconds"] = "Enter a time between 1 minute and 100 hours."

    def _clean_threshold(self, errors: dict[str, str]) -> None:
        self._must_be_empty(errors, ["discipline", "distance_m", "target_time_seconds"])
        if not self.metric:
            errors["metric"] = "A threshold goal needs FTP or threshold pace."
        elif self.metric in self.Metric.values:
            if self.target_value is None:
                errors["target_value"] = "A threshold goal needs a target value."
            else:
                rule = RULES[(_SPORT_OF_METRIC[self.metric], self.metric)]
                value: Any = self.target_value
                if not _within(value, rule.minimum, rule.maximum, False):
                    span = f"{rule.minimum:g} and {rule.maximum:g} {rule.unit}"
                    errors["target_value"] = f"Enter a value between {span}."

    def _must_be_empty(self, errors: dict[str, str], names: list[str]) -> None:
        for name in names:
            if getattr(self, name) not in (None, ""):
                errors.setdefault(
                    name, f"Does not apply to a {self.get_kind_display().lower()} goal."
                )


def _within(value: object, minimum: float, maximum: float, above_minimum: bool) -> bool:
    """A number between the limits; ``above_minimum``: strictly above the lower one."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return False  # NaN and infinity fail the comparisons below
    return (value > minimum if above_minimum else value >= minimum) and value <= maximum
