import uuid
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q

from core.models import OwnedModel

from .schema import DURATION_MAX, NOTES_MAX, RATIONALE_MAX, TITLE_MAX, ZONE_COUNT

REASON_MAX = 200
# The other limits are those of the format in ``planning.schema``, the single source.


class WeeklyPlan(OwnedModel):
    """One version of the training plan of one week (Monday to Sunday).

    A plan is never changed once it is confirmed: a change is a new version of the same week, which
    points to the one it replaces (``parent``) and says why (``reason``). At most one version of a
    week is confirmed at a time; the one it replaces becomes ``superseded``. ``rationale`` is the
    explanation of the coach for the user: free text, shown as text and never interpreted.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        CONFIRMED = "confirmed", "Confirmed"
        SUPERSEDED = "superseded", "Superseded"
        DISCARDED = "discarded", "Discarded"

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    week_start = models.DateField()
    version = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    # The version this one replaces. If that is deleted the link is lost, the plan stays.
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="revisions"
    )
    reason = models.CharField(max_length=REASON_MAX, blank=True)
    rationale = models.CharField(max_length=RATIONALE_MAX, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    # Set when the plan is confirmed and kept when it is superseded; empty for drafts.
    confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(week_start__iso_week_day=1), name="planning_week_starts_on_monday"
            ),
            models.CheckConstraint(condition=Q(version__gte=1), name="planning_version_from_one"),
            models.UniqueConstraint(
                fields=["owner", "week_start", "version"], name="planning_one_per_version"
            ),
            models.UniqueConstraint(
                fields=["owner", "week_start"],
                condition=Q(status="confirmed"),
                name="planning_one_confirmed_per_week",
            ),
            models.CheckConstraint(
                condition=(
                    Q(status__in=["confirmed", "superseded"], confirmed_at__isnull=False)
                    | Q(status__in=["draft", "discarded"], confirmed_at__isnull=True)
                ),
                name="planning_confirmed_at_matches_status",
            ),
            models.CheckConstraint(
                condition=~Q(parent=F("id")), name="planning_not_its_own_parent"
            ),
        ]
        indexes = [models.Index(fields=["owner", "week_start"], name="planning_owner_week")]

    def __str__(self) -> str:
        # No reason or rationale: they are free text and have no business in logs.
        return f"Plan of user {self.owner_id} for the week of {self.week_start} (v{self.version})"

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if self.week_start is not None and self.week_start.weekday() != 0:
            errors["week_start"] = "A week starts on a Monday."
        parent = self.parent if self.parent_id is not None else None
        if parent is not None:
            if parent.owner_id != self.owner_id or parent.week_start != self.week_start:
                errors["parent"] = "A version replaces a version of the same week."
            elif self.version is not None and self.version <= parent.version:
                errors["version"] = "A version must be newer than the one it replaces."
        if errors:
            raise ValidationError(errors)


class PlannedWorkout(OwnedModel):
    """One workout of a plan, with its intensity target and an optional interval structure.

    ``segments`` is a list of dictionaries in the format of ``planning.schema`` (checked there,
    not by the database). ``zone_system`` and ``zone`` give the target of the whole session when
    there are no segments; both are set or both are empty.
    """

    class Sport(models.TextChoices):
        RUNNING = "running", "Running"
        CYCLING = "cycling", "Cycling"
        SWIMMING = "swimming", "Swimming"
        STRENGTH = "strength", "Strength"

    class Goal(models.TextChoices):
        RECOVERY = "recovery", "Recovery"
        ENDURANCE = "endurance", "Endurance"
        TEMPO = "tempo", "Tempo"
        THRESHOLD = "threshold", "Threshold"
        VO2MAX = "vo2max", "VO2max"
        STRENGTH = "strength", "Strength"
        OTHER = "other", "Other"

    class ZoneSystem(models.TextChoices):
        POWER = "power", "Power"
        HEART_RATE = "heart_rate", "Heart rate"
        PACE = "pace", "Pace"

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    plan = models.ForeignKey(WeeklyPlan, on_delete=models.CASCADE, related_name="workouts")
    day = models.DateField()
    # The order within a day.
    position = models.PositiveSmallIntegerField(default=0)
    sport = models.CharField(max_length=20, choices=Sport.choices)
    title = models.CharField(max_length=TITLE_MAX)
    goal = models.CharField(max_length=20, choices=Goal.choices)
    duration_minutes = models.PositiveSmallIntegerField()
    segments = models.JSONField(default=list, blank=True)
    zone_system = models.CharField(max_length=20, choices=ZoneSystem.choices, blank=True)
    zone = models.PositiveSmallIntegerField(null=True, blank=True)
    notes = models.CharField(max_length=NOTES_MAX, blank=True)

    class Meta:
        ordering = ["day", "position", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["plan", "day", "position"], name="planning_one_workout_per_slot"
            ),
            models.CheckConstraint(condition=~Q(title=""), name="planning_workout_has_a_title"),
            models.CheckConstraint(
                condition=Q(duration_minutes__gte=1, duration_minutes__lte=DURATION_MAX),
                name="planning_duration_in_range",
            ),
            models.CheckConstraint(
                condition=(
                    Q(zone_system="", zone__isnull=True)
                    | (~Q(zone_system="") & Q(zone__isnull=False))
                ),
                name="planning_zone_with_its_system",
            ),
            models.CheckConstraint(
                condition=(
                    Q(zone__isnull=True)
                    | (
                        Q(zone__gte=1)
                        & (
                            Q(zone_system="power", zone__lte=ZONE_COUNT["power"])
                            | Q(zone_system="heart_rate", zone__lte=ZONE_COUNT["heart_rate"])
                            | Q(zone_system="pace", zone__lte=ZONE_COUNT["pace"])
                        )
                    )
                ),
                name="planning_zone_exists_in_its_system",
            ),
        ]

    def __str__(self) -> str:
        # No title and no notes: they are free text and have no business in logs.
        return f"{self.sport} workout of user {self.owner_id} on {self.day}"

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if self.plan_id is not None:
            plan = self.plan
            if self.owner_id is not None and plan.owner_id != self.owner_id:
                errors["plan"] = "A workout belongs to a plan of the same user."
            if self.day is not None and not (
                plan.week_start <= self.day <= plan.week_start + timedelta(days=6)
            ):
                errors["day"] = "The day lies outside the week of the plan."
        if not isinstance(self.segments, list):
            errors["segments"] = "Segments are a list."
        if errors:
            raise ValidationError(errors)
