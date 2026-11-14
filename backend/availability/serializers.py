"""Input checks and the shape of what the availability API answers.

Strict like the goals API: a number is a JSON number, text is text, and nothing is turned into
something else on the way in.
"""

from datetime import date
from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from accounts.models import User
from goals.serializers import TextField, WholeNumberField
from goals.services import today_of

from .models import (
    DAY_MINUTES_MAX,
    LIMITATIONS_MAX,
    NOTE_MAX,
    WEEK_MINUTES_MAX,
    AvailabilitySettings,
    UnavailablePeriod,
    WeekdayMinutes,
)

WEEKDAYS = "Enter seven numbers of minutes, Monday first."
DAY_RANGE = f"Enter whole minutes between 0 and {DAY_MINUTES_MAX} for every day."
BUDGET_RANGE = f"Enter whole minutes between 0 and {WEEK_MINUTES_MAX}."
MAX_PERIODS = 100
TOO_MANY_PERIODS = f"You can have at most {MAX_PERIODS} periods. Delete one first."

# What a client may send for a period; everything else (id, owner, the computed fields) is ours.
PERIOD_WRITABLE = ("kind", "start_date", "end_date", "note")


class WeekdaysField(serializers.Field[list[int], list[int], list[int], Any]):
    """Seven whole numbers of minutes, Monday first. One flat message, not one per element."""

    def to_internal_value(self, data: Any) -> list[int]:
        if not isinstance(data, list) or len(data) != 7:
            raise serializers.ValidationError(WEEKDAYS)
        for minutes in data:
            if isinstance(minutes, bool) or not isinstance(minutes, int):
                raise serializers.ValidationError(DAY_RANGE)
            if not 0 <= minutes <= DAY_MINUTES_MAX:
                raise serializers.ValidationError(DAY_RANGE)
        return list(data)

    def to_representation(self, value: list[int]) -> list[int]:
        return value


class AvailabilityInput(serializers.Serializer[Any]):
    """What may be sent: any of the four, the rest stays as it is."""

    weekdays = WeekdaysField(required=False)
    weekly_budget_minutes = WholeNumberField(
        min_value=0,
        max_value=WEEK_MINUTES_MAX,
        allow_null=True,
        required=False,
        error_messages={
            "invalid": BUDGET_RANGE,
            "min_value": BUDGET_RANGE,
            "max_value": BUDGET_RANGE,
        },
    )
    # The same range as the budget: a number of minutes in a week, or ``null`` for none.
    typical_weekly_minutes = WholeNumberField(
        min_value=0,
        max_value=WEEK_MINUTES_MAX,
        allow_null=True,
        required=False,
        error_messages={
            "invalid": BUDGET_RANGE,
            "min_value": BUDGET_RANGE,
            "max_value": BUDGET_RANGE,
        },
    )
    limitations = TextField(max_length=LIMITATIONS_MAX, allow_blank=True, required=False)


def availability_data(
    settings: AvailabilitySettings | None, weekdays: list[WeekdayMinutes]
) -> dict[str, Any]:
    """The answer: the seven weekdays (Monday first, 0 where nothing is saved), the weekly budget
    and the typical week (``null`` for none) and the limitations. No row ids, no owner."""
    minutes = [0] * 7
    for row in weekdays:
        minutes[row.weekday] = row.minutes
    return {
        "weekdays": minutes,
        "weekly_budget_minutes": settings.weekly_budget_minutes if settings else None,
        "typical_weekly_minutes": settings.typical_weekly_minutes if settings else None,
        "limitations": settings.limitations if settings else "",
    }


class PeriodSerializer(serializers.ModelSerializer[UnavailablePeriod]):
    note = TextField(max_length=NOTE_MAX, allow_blank=True, required=False)
    days = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()

    class Meta:
        model = UnavailablePeriod
        fields = ["id", "kind", "start_date", "end_date", "days", "status", "note"]
        read_only_fields = ["id", "days", "status"]
        # The rules are checked in ``validate`` through the model's ``clean``.
        validators: list[Any] = []

    # --- output

    def get_days(self, period: UnavailablePeriod) -> int:
        """How many days the period covers, both ends included."""
        return (period.end_date - period.start_date).days + 1

    def get_status(self, period: UnavailablePeriod) -> str:
        """``current`` (today is inside), ``upcoming`` or ``past``, by the user's own today."""
        today = self._today()
        if period.end_date < today:
            return "past"
        return "upcoming" if period.start_date > today else "current"

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
        candidate = self._candidate(attrs)
        try:
            candidate.clean()
        except DjangoValidationError as error:
            raise serializers.ValidationError(error.message_dict) from None
        if (
            self.instance is None
            and UnavailablePeriod.objects.for_user(self._user()).count() >= MAX_PERIODS
        ):
            raise serializers.ValidationError({"non_field_errors": [TOO_MANY_PERIODS]})
        return attrs

    def _candidate(self, attrs: dict[str, Any]) -> UnavailablePeriod:
        """The period as it would be after this change, not saved."""
        base = (
            {name: getattr(self.instance, name) for name in PERIOD_WRITABLE}
            if self.instance is not None
            else {}
        )
        return UnavailablePeriod(
            **(base | {name: value for name, value in attrs.items() if name in PERIOD_WRITABLE})
        )
