import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

from activities.models import Activity
from core.models import OwnedModel
from planning.models import PlannedWorkout

NOTES_MAX = 500
# The scales of the week feedback: fatigue, motivation and pain, each 1 (little) to 5 (a lot).
SCALE_MIN = 1
SCALE_MAX = 5
# The longest comment of the coach that is kept.
COMMENT_MAX = 600


class WorkoutReview(OwnedModel):
    """What the user decided about one planned workout when reviewing the week.

    The match of activities to workouts and the status are computed (``reviews.matching``); this
    row holds only the user's own word, and a workout without one has no row. A confirmed plan is
    never changed, which is why the decision is kept beside the workout and not in it.

    ``activity`` links the workout to the activity of the user's choice and ``no_activity`` says
    that none belongs to it (never both). ``status`` sets how it went; empty: worked out from the
    activity. If the activity is deleted the link is gone, the rest of the decision stays.
    """

    class Status(models.TextChoices):
        # The statuses that can be chosen: ``open`` is only ever computed.
        DONE = "done", "Done"
        PARTIAL = "partial", "Partial"
        MISSED = "missed", "Missed"
        REPLACED = "replaced", "Replaced"

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    workout = models.OneToOneField(PlannedWorkout, on_delete=models.CASCADE, related_name="review")
    activity = models.ForeignKey(
        Activity,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="workout_reviews",
    )
    no_activity = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=Status.choices, blank=True)

    class Meta:
        constraints = [
            # An activity belongs to one workout.
            models.UniqueConstraint(
                fields=["owner", "activity"],
                condition=Q(activity__isnull=False),
                name="reviews_one_workout_per_activity",
            ),
            models.CheckConstraint(
                condition=~(Q(activity__isnull=False) & Q(no_activity=True)),
                name="reviews_activity_or_none_not_both",
            ),
            models.CheckConstraint(
                condition=Q(status__in=["", "done", "partial", "missed", "replaced"]),
                name="reviews_status_is_known",
            ),
        ]

    def __str__(self) -> str:
        return f"Review of a workout of user {self.owner_id}"

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if self.owner_id is not None:
            if self.workout_id is not None and self.workout.owner_id != self.owner_id:
                errors["workout"] = "A review belongs to a workout of the same user."
            activity = self.activity
            if activity is not None and activity.owner_id != self.owner_id:
                errors["activity"] = "A review links an activity of the same user."
        if self.activity_id is not None and self.no_activity:
            errors["no_activity"] = "A workout has an activity or none, not both."
        if errors:
            raise ValidationError(errors)


class WeekFeedback(OwnedModel):
    """How the user felt about one week (Monday to Sunday): at most one per user and week, which
    can be changed at any time. Every scale may be left empty; ``verdict`` is the week as a whole in
    one of four fixed words (empty: none given); ``notes`` is the user's own free text, shown as
    text and never interpreted (and never sent to the coach)."""

    class Verdict(models.TextChoices):
        BAD = "bad", "Bad"
        FAIR = "fair", "Fair"
        GOOD = "good", "Good"
        STRONG = "strong", "Strong"

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    week_start = models.DateField()
    fatigue = models.PositiveSmallIntegerField(null=True, blank=True)
    motivation = models.PositiveSmallIntegerField(null=True, blank=True)
    pain = models.PositiveSmallIntegerField(null=True, blank=True)
    verdict = models.CharField(max_length=10, choices=Verdict.choices, blank=True)
    notes = models.CharField(max_length=NOTES_MAX, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["owner", "week_start"], name="reviews_one_per_week"),
            models.CheckConstraint(
                condition=Q(verdict__in=["", "bad", "fair", "good", "strong"]),
                name="reviews_feedback_verdict_is_known",
            ),
            models.CheckConstraint(
                condition=Q(week_start__iso_week_day=1), name="reviews_feedback_week_is_a_monday"
            ),
            *(
                models.CheckConstraint(
                    condition=Q(**{f"{field}__isnull": True})
                    | Q(**{f"{field}__gte": SCALE_MIN, f"{field}__lte": SCALE_MAX}),
                    name=f"reviews_{field}_in_range",
                )
                for field in ("fatigue", "motivation", "pain")
            ),
        ]

    def __str__(self) -> str:
        # No notes: they are free text and have no business in logs.
        return f"Feedback of user {self.owner_id} for the week of {self.week_start}"

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if self.week_start is not None and self.week_start.weekday() != 0:
            errors["week_start"] = "A week starts on a Monday."
        if errors:
            raise ValidationError(errors)


class WeekComment(OwnedModel):
    """What the user's coach said about one week (Monday to Sunday) when asked: a short comment
    and what to do with the next week. At most one per user and week; asking again replaces it.

    ``comment`` is the coach's own text: free text, shown as text and never interpreted, and never
    sent back to the coach. ``next_week`` is one of three fixed words, which the next week plan is
    told. ``created_at`` is when it was written.
    """

    class NextWeek(models.TextChoices):
        INCREASE = "increase", "Increase"
        HOLD = "hold", "Hold"
        REDUCE = "reduce", "Reduce"

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    week_start = models.DateField()
    comment = models.CharField(max_length=COMMENT_MAX)
    next_week = models.CharField(max_length=20, choices=NextWeek.choices)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "week_start"], name="reviews_one_comment_per_week"
            ),
            models.CheckConstraint(
                condition=Q(week_start__iso_week_day=1), name="reviews_comment_week_is_a_monday"
            ),
            models.CheckConstraint(condition=~Q(comment=""), name="reviews_comment_not_empty"),
            models.CheckConstraint(
                condition=Q(next_week__in=["increase", "hold", "reduce"]),
                name="reviews_next_week_is_known",
            ),
        ]

    def __str__(self) -> str:
        # No comment: it is free text and has no business in logs.
        return f"Comment for user {self.owner_id} on the week of {self.week_start}"

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if self.week_start is not None and self.week_start.weekday() != 0:
            errors["week_start"] = "A week starts on a Monday."
        if errors:
            raise ValidationError(errors)
