import uuid
from datetime import timedelta
from typing import Any

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from core.models import OwnedModel

from .schema import (
    DURATION_MAX,
    NOTES_MAX,
    RATIONALE_MAX,
    STRETCHING_MAX,
    TITLE_MAX,
    ZONE_COUNT,
)

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

    class Slot(models.TextChoices):
        MORNING = "morning", "Morning"
        AFTERNOON = "afternoon", "Afternoon"
        EVENING = "evening", "Evening"

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
    # When on the day; empty: not said. The ``position`` follows the order of the times of day.
    slot = models.CharField(max_length=20, choices=Slot.choices, blank=True)
    # Stretching added to this workout (0: none): never a workout of its own.
    stretching_minutes = models.PositiveSmallIntegerField(default=0)
    # Which training this is across the versions of a week: a version made from another (changed by
    # hand, restored) keeps the lineage of the workouts it copies, a new workout gets a new one.
    # Sending to Intervals.icu and the corrections of the week review follow the lineage, so that a
    # change updates the same calendar event and keeps what the user said about the session.
    lineage = models.UUIDField(default=uuid.uuid7, editable=False)

    class Meta:
        ordering = ["day", "position", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["plan", "day", "position"], name="planning_one_workout_per_slot"
            ),
            models.UniqueConstraint(
                fields=["plan", "lineage"], name="planning_one_workout_per_lineage"
            ),
            models.CheckConstraint(condition=~Q(title=""), name="planning_workout_has_a_title"),
            models.CheckConstraint(
                condition=Q(slot__in=["", "morning", "afternoon", "evening"]),
                name="planning_slot_is_known",
            ),
            models.CheckConstraint(
                condition=Q(stretching_minutes__lte=STRETCHING_MAX),
                name="planning_stretching_in_range",
            ),
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

    def save(self, *args: Any, **kwargs: Any) -> None:
        # A plan that is no draft any more is a record of what was agreed: its workouts are never
        # added to or changed (a change is a new version of the week).
        if self.plan.status != WeeklyPlan.Status.DRAFT:
            raise ValidationError("The workouts of a plan that is not a draft cannot be changed.")
        super().save(*args, **kwargs)

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


class WorkoutExport(OwnedModel):
    """What PaceForge knows about one event it put into the user's Intervals.icu calendar.

    ``external_id`` is the key at Intervals.icu (the same id again updates the same event) and is
    made from the lineage of the workout, so a version of a week that was made from another keeps
    the keys of the workouts it copies, and a version the coach drafted anew, whose workouts are
    new, has other keys. The row stays when the workout is gone (the plan was deleted, or a newer
    version was pushed instead): it is what lets the next push remove the event from the calendar.

    ``error_code`` is one of the fixed codes of ``planning.push``, never what Intervals.icu said or
    anything of the workout.
    """

    class Status(models.TextChoices):
        SYNCED = "synced", "Synced"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    # The Monday of the week the workout belongs to: all events of a week are handled together.
    week_start = models.DateField()
    workout = models.ForeignKey(
        PlannedWorkout, null=True, blank=True, on_delete=models.SET_NULL, related_name="exports"
    )
    external_id = models.CharField(max_length=100)
    # The id of the event at Intervals.icu; empty until the event has been created. A failed
    # update keeps it: the event is still there.
    event_id = models.PositiveBigIntegerField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices)
    error_code = models.CharField(max_length=40, blank=True)
    # The time of the last attempt, successful or not.
    pushed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "external_id"], name="planning_one_export_per_external_id"
            ),
            models.CheckConstraint(
                condition=Q(week_start__iso_week_day=1), name="planning_export_week_is_a_monday"
            ),
            models.CheckConstraint(
                condition=(
                    Q(status="synced", event_id__isnull=False, error_code="")
                    | (Q(status="failed") & ~Q(error_code=""))
                ),
                name="planning_export_state_is_consistent",
            ),
        ]
        indexes = [models.Index(fields=["owner", "week_start"], name="planning_export_owner_week")]

    def __str__(self) -> str:
        return f"Export of user {self.owner_id} for the week of {self.week_start} ({self.status})"
