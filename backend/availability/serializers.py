"""Input checks and the shape of what the availability API answers.

Strict like the goals API: a number is a JSON number, text is text, and nothing is turned into
something else on the way in.
"""

from typing import Any

from rest_framework import serializers

from goals.serializers import TextField, WholeNumberField

from .models import (
    DAY_MINUTES_MAX,
    LIMITATIONS_MAX,
    WEEK_MINUTES_MAX,
    AvailabilitySettings,
    WeekdayMinutes,
)

WEEKDAYS = "Enter seven numbers of minutes, Monday first."
DAY_RANGE = f"Enter whole minutes between 0 and {DAY_MINUTES_MAX} for every day."
BUDGET_RANGE = f"Enter whole minutes between 0 and {WEEK_MINUTES_MAX}."


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
    """What may be sent: any of the three, the rest stays as it is."""

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
    limitations = TextField(max_length=LIMITATIONS_MAX, allow_blank=True, required=False)


def availability_data(
    settings: AvailabilitySettings | None, weekdays: list[WeekdayMinutes]
) -> dict[str, Any]:
    """The answer: the seven weekdays (Monday first, 0 where nothing is saved), the weekly budget
    (``null`` for none) and the limitations. No row ids, no owner."""
    minutes = [0] * 7
    for row in weekdays:
        minutes[row.weekday] = row.minutes
    return {
        "weekdays": minutes,
        "weekly_budget_minutes": settings.weekly_budget_minutes if settings else None,
        "limitations": settings.limitations if settings else "",
    }
