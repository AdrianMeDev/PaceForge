from datetime import date
from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from accounts.models import User
from athletes.serializers import NumberField

from .assessing import assess_goals
from .models import NOTES_MAX, TITLE_MAX, Goal
from .realism import Assessment
from .services import today_of

MAX_GOALS = 30
MAIN_TAKEN = "You already have a main goal. Change it first."
PAST_RACE = (
    "An active race cannot lie in the past. Choose a later date, or mark it achieved or dropped."
)
KIND_FIXED = "The kind of a goal cannot be changed."
TOO_MANY = f"You can have at most {MAX_GOALS} goals. Delete one first."

# What a client may send; everything else (id, owner, times) is the server's.
WRITABLE = (
    "kind", "title", "notes", "priority", "status", "target_date", "discipline",
    "distance_m", "target_time_seconds", "metric", "target_value",
)  # fmt: skip

# Fields that are an empty text in the database and ``null`` in the API.
_NULLABLE_TEXTS = ("discipline", "metric")


class TextField(serializers.CharField):
    """Text. A number or a list is not turned into text: that would hide a client's mistake."""

    def to_internal_value(self, data: Any) -> str:
        if not isinstance(data, str):
            self.fail("invalid")
        return super().to_internal_value(data)


class WholeNumberField(serializers.IntegerField):
    """A JSON integer. Text such as "3600", fractions and true/false are not integers."""

    def to_internal_value(self, data: Any) -> int:
        if isinstance(data, bool) or not isinstance(data, int):
            self.fail("invalid")
        return super().to_internal_value(data)


class GoalSerializer(serializers.ModelSerializer[Goal]):
    title = TextField(max_length=TITLE_MAX)
    notes = TextField(max_length=NOTES_MAX, allow_blank=True, required=False)
    discipline = serializers.ChoiceField(
        choices=Goal.Discipline.choices, allow_null=True, required=False
    )
    metric = serializers.ChoiceField(choices=Goal.Metric.choices, allow_null=True, required=False)
    distance_m = NumberField(allow_null=True, required=False)
    target_time_seconds = WholeNumberField(allow_null=True, required=False)
    target_value = NumberField(allow_null=True, required=False)
    days_to_go = serializers.SerializerMethodField()
    assessment = serializers.SerializerMethodField()

    class Meta:
        model = Goal
        fields = [
            "id",
            "kind",
            "title",
            "notes",
            "priority",
            "status",
            "target_date",
            "discipline",
            "distance_m",
            "target_time_seconds",
            "metric",
            "target_value",
            "days_to_go",
            "assessment",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "days_to_go", "assessment", "created_at", "updated_at"]
        # The rules are checked in ``validate`` (the unique-together helpers of the framework do
        # not know the condition of the main goal rule).
        validators: list[Any] = []

    # --- output

    def get_days_to_go(self, goal: Goal) -> int | None:
        return None if goal.target_date is None else (goal.target_date - self._today()).days

    def get_assessment(self, goal: Goal) -> dict[str, Any] | None:
        """How realistic the target is (``goals.realism``), for an active goal that has a target to
        judge; ``null`` otherwise. A view that lists goals puts all of them in the context at once;
        a single goal is looked up on its own."""
        if goal.kind == Goal.Kind.GENERAL or goal.status != Goal.Status.ACTIVE:
            return None
        cache = self.context.get("assessments")
        if not isinstance(cache, dict):
            cache = {}  # no view to share it: this goal alone
        if goal.pk not in cache:
            cache.update(assess_goals(self._user(), [goal], self._today()))
        return assessment_data(cache[goal.pk])

    def to_representation(self, instance: Goal) -> dict[str, Any]:
        data = super().to_representation(instance)
        for name in _NULLABLE_TEXTS:
            data[name] = data[name] or None
        return data

    def _today(self) -> date:
        # The view puts it in the context once per request; without a view it is looked up.
        today = self.context.get("today")
        return today if isinstance(today, date) else today_of(self._user())

    def _user(self) -> User:
        user = self.context["request"].user
        assert isinstance(user, User)
        return user

    # --- input

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        instance = self.instance
        for name in _NULLABLE_TEXTS:
            if name in attrs and attrs[name] is None:
                attrs[name] = ""
        if instance is not None and attrs.get("kind", instance.kind) != instance.kind:
            raise serializers.ValidationError({"kind": [KIND_FIXED]})

        candidate = self._candidate(attrs)
        try:
            candidate.clean()
        except DjangoValidationError as error:
            raise serializers.ValidationError(error.message_dict) from None

        self._check_the_date(candidate)
        self._check_the_main_goal(candidate)
        if instance is None and Goal.objects.for_user(self._user()).count() >= MAX_GOALS:
            raise serializers.ValidationError({"non_field_errors": [TOO_MANY]})
        return attrs

    def _candidate(self, attrs: dict[str, Any]) -> Goal:
        """The goal as it would be after this change, not saved."""
        base = (
            {name: getattr(self.instance, name) for name in WRITABLE}
            if self.instance is not None
            else {}
        )
        return Goal(**(base | {name: value for name, value in attrs.items() if name in WRITABLE}))

    def _check_the_date(self, goal: Goal) -> None:
        """A race that becomes active, or whose date changes while active, must not lie in the
        past. A past race that stays as it is (its title changes, say) is left alone."""
        if goal.kind != Goal.Kind.RACE or goal.status != Goal.Status.ACTIVE:
            return
        if goal.target_date is None or goal.target_date >= self._today():
            return
        before = self.instance
        unchanged = (
            before is not None
            and before.status == Goal.Status.ACTIVE
            and before.target_date == goal.target_date
        )
        if not unchanged:
            raise serializers.ValidationError({"target_date": [PAST_RACE]})

    def _check_the_main_goal(self, goal: Goal) -> None:
        if (goal.priority, goal.status) != (Goal.Priority.MAIN, Goal.Status.ACTIVE):
            return
        others = Goal.objects.for_user(self._user()).filter(
            priority=Goal.Priority.MAIN, status=Goal.Status.ACTIVE
        )
        if self.instance is not None:
            others = others.exclude(pk=self.instance.pk)
        if others.exists():
            raise serializers.ValidationError({"priority": [MAIN_TAKEN]})


def assessment_data(found: Assessment) -> dict[str, Any]:
    """The judgement as the API tells it: fixed words and numbers, nothing of the athlete's text."""
    return {
        "rating": found.rating.value,
        "reason": None if found.reason is None else found.reason.value,
        "current": found.current,
        "needed": found.needed,
        "suggested": found.suggested,
        "weeks": found.weeks,
        "prep_short": found.prep_short,
        "prep_weeks": found.prep_weeks,
    }
