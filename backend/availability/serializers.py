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

from .intensity import (
    DEFAULT_LEVEL,
    LEVEL_LIMITS,
    LIMIT_NAMES,
    LIMIT_RANGES,
    IntensityLevel,
    limit_problems,
    range_message,
)
from .models import (
    DAY_MINUTES_MAX,
    FIXED_MINUTES_MAX,
    FIXED_MINUTES_MIN,
    LIMITATIONS_MAX,
    MINIMUM_ABOVE_BUDGET,
    NOTE_MAX,
    SESSIONS_PER_WEEK_MAX,
    SLOTS,
    SPORTS,
    TRAINING_DAYS_MAX,
    TRAINING_DAYS_MIN,
    WEEK_MINUTES_MAX,
    WEEKDAY_MAX,
    AvailabilitySettings,
    BodyPart,
    FixedSession,
    Limitation,
    LimitationStatus,
    SportPreference,
    SportRole,
    StrengthFocus,
    UnavailablePeriod,
    WeekdayMinutes,
    effective_sports,
)

WEEKDAYS = "Enter seven numbers of minutes, Monday first."
DAY_RANGE = f"Enter whole minutes between 0 and {DAY_MINUTES_MAX} for every day."
BUDGET_RANGE = f"Enter whole minutes between 0 and {WEEK_MINUTES_MAX}."
SPORTS_CHOICE = f"Choose at least one of: {', '.join(SPORTS)}."
STRETCHING_CHOICE = "Send true or false."
DOUBLE_DAYS = "Enter seven values of true or false, Monday first."
TIME_WINDOWS = (
    "Enter seven lists of parts of the day, Monday first, each with at least one of: "
    f"{', '.join(SLOTS)}."
)
SHARE_CHOICE = "Send true or false."
SPORT_PREFERENCES = (
    f"Send an object with {', '.join(SPORTS)}, each holding role, sessions_min and sessions_max "
    f"(role is one of {', '.join(SportRole.values)} or null)."
)
SESSIONS_RANGE = (
    f"Enter a whole number of sessions between 0 and {SESSIONS_PER_WEEK_MAX}, "
    "the least not above the most."
)
STRENGTH_FOCUS_CHOICE = f"Choose one of: {', '.join(StrengthFocus.values)}."
TRAINING_DAYS_RANGE = (
    f"Enter a whole number of days between {TRAINING_DAYS_MIN} and {TRAINING_DAYS_MAX}."
)
LONG_DAY_RANGE = f"Choose a weekday from 0 (Monday) to {WEEKDAY_MAX} (Sunday)."
BUDGET_BELOW_MINIMUM = "The weekly budget cannot be below your minimum."
LEVEL_CHOICE = f"Choose one of: {', '.join(IntensityLevel.values)}."
MAX_PERIODS = 100
TOO_MANY_PERIODS = f"You can have at most {MAX_PERIODS} periods. Delete one first."
MAX_LIMITATIONS = 50
TOO_MANY_LIMITATIONS = f"You can have at most {MAX_LIMITATIONS} limitations. Delete one first."
BODY_PART_CHOICE = f"Choose one of: {', '.join(BodyPart.values)}."
LIMITATION_STATUS_CHOICE = f"Choose one of: {', '.join(LimitationStatus.values)}."
LIMITATION_SPORTS_CHOICE = f"Choose any of: {', '.join(SPORTS)}, or none."
MAX_FIXED_SESSIONS = 14
TOO_MANY_FIXED_SESSIONS = (
    f"You can have at most {MAX_FIXED_SESSIONS} fixed appointments. Delete one first."
)
FIXED_WEEKDAY_CHOICE = f"Choose a weekday from 0 (Monday) to {WEEKDAY_MAX} (Sunday)."
FIXED_SPORT_CHOICE = f"Choose one of: {', '.join(SPORTS)}."
FIXED_MINUTES_RANGE = (
    f"Enter a whole number of minutes between {FIXED_MINUTES_MIN} and {FIXED_MINUTES_MAX}."
)
FIXED_SLOT_CHOICE = f"Choose one of: {', '.join(SLOTS)}, or null for no part of the day."

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


class SportsField(serializers.Field[list[str], list[str], list[str], Any]):
    """At least one sport, each of the known ones at most once. Stored in the order of ``SPORTS``,
    whatever the order sent."""

    def to_internal_value(self, data: Any) -> list[str]:
        if (
            not isinstance(data, list)
            or not data
            or not all(isinstance(sport, str) and sport in SPORTS for sport in data)
            or len(set(data)) != len(data)
        ):
            raise serializers.ValidationError(SPORTS_CHOICE)
        return [sport for sport in SPORTS if sport in data]

    def to_representation(self, value: list[str]) -> list[str]:
        return value


class DoubleDaysField(serializers.Field[list[bool], list[bool], list[bool], Any]):
    """Seven ``true`` or ``false``, Monday first: whether two sessions are allowed on the day."""

    def to_internal_value(self, data: Any) -> list[bool]:
        if (
            not isinstance(data, list)
            or len(data) != 7
            or not all(isinstance(flag, bool) for flag in data)
        ):
            raise serializers.ValidationError(DOUBLE_DAYS)
        return list(data)

    def to_representation(self, value: list[bool]) -> list[bool]:
        return value


class TimeWindowsField(serializers.Field[list[list[str]], list[list[str]], list[list[str]], Any]):
    """Seven lists of parts of the day, Monday first. Each has at least one of the known ones, each
    at most once; it is stored in the order of the day, whatever the order sent."""

    def to_internal_value(self, data: Any) -> list[list[str]]:
        if not isinstance(data, list) or len(data) != 7:
            raise serializers.ValidationError(TIME_WINDOWS)
        windows = []
        for day in data:
            if (
                not isinstance(day, list)
                or not day
                or not all(isinstance(slot, str) and slot in SLOTS for slot in day)
                or len(set(day)) != len(day)
            ):
                raise serializers.ValidationError(TIME_WINDOWS)
            windows.append([slot for slot in SLOTS if slot in day])
        return windows

    def to_representation(self, value: list[list[str]]) -> list[list[str]]:
        return value


class SportPreferencesField(serializers.Field[Any, Any, Any, Any]):
    """What each sport is for the user: all four sports, each with a role (or ``null``) and the
    least and the most sessions a week (or ``null``). Sent as a whole: a missing sport, an unknown
    key, a role that does not exist or a count out of range is refused with one flat message."""

    KEYS = {"role", "sessions_min", "sessions_max"}

    def to_internal_value(self, data: Any) -> dict[str, dict[str, Any]]:
        if not isinstance(data, dict) or set(data) != set(SPORTS):
            raise serializers.ValidationError(SPORT_PREFERENCES)
        result: dict[str, dict[str, Any]] = {}
        for sport in SPORTS:
            item = data[sport]
            if not isinstance(item, dict) or set(item) != self.KEYS:
                raise serializers.ValidationError(SPORT_PREFERENCES)
            role = item["role"]
            if role is not None and (not isinstance(role, str) or role not in SportRole.values):
                raise serializers.ValidationError(SPORT_PREFERENCES)
            counts = [item["sessions_min"], item["sessions_max"]]
            for count in counts:
                if count is not None and (
                    isinstance(count, bool)
                    or not isinstance(count, int)
                    or not 0 <= count <= SESSIONS_PER_WEEK_MAX
                ):
                    raise serializers.ValidationError(SESSIONS_RANGE)
            low, high = counts
            if low is not None and high is not None and low > high:
                raise serializers.ValidationError(SESSIONS_RANGE)
            result[sport] = {"role": role or "", "sessions_min": low, "sessions_max": high}
        return result

    def to_representation(self, value: Any) -> Any:
        return value


class StrictBooleanField(serializers.Field[bool, bool, bool, Any]):
    """``true`` or ``false`` and nothing else: no ``"true"``, no ``1``."""

    def to_internal_value(self, data: Any) -> bool:
        if not isinstance(data, bool):
            raise serializers.ValidationError(STRETCHING_CHOICE)
        return data

    def to_representation(self, value: bool) -> bool:
        return value


def _own_limit_field(name: str) -> WholeNumberField:
    """A whole number in the range of the limit ``name``, or ``null`` for the level's value."""
    low, high = LIMIT_RANGES[name]
    message = range_message(name)
    return WholeNumberField(
        min_value=low,
        max_value=high,
        allow_null=True,
        required=False,
        error_messages={"invalid": message, "min_value": message, "max_value": message},
    )


class AvailabilityInput(serializers.Serializer[Any]):
    """What may be sent: any of the fields, the rest stays as it is.

    The own limits are checked against each other and the level as they will be after saving: what
    is sent, and what is stored for the rest (``context["settings"]``, ``None`` if nothing is).
    """

    weekdays = WeekdaysField(required=False)
    double_days = DoubleDaysField(required=False, error_messages={"null": DOUBLE_DAYS})
    time_windows = TimeWindowsField(required=False, error_messages={"null": TIME_WINDOWS})
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
    training_days = WholeNumberField(
        min_value=TRAINING_DAYS_MIN,
        max_value=TRAINING_DAYS_MAX,
        allow_null=True,
        required=False,
        error_messages={
            "invalid": TRAINING_DAYS_RANGE,
            "min_value": TRAINING_DAYS_RANGE,
            "max_value": TRAINING_DAYS_RANGE,
        },
    )
    # The least the user wants to train in a week: the same range as the budget, and never above it.
    min_weekly_minutes = WholeNumberField(
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
    long_run_day = WholeNumberField(
        min_value=0,
        max_value=WEEKDAY_MAX,
        allow_null=True,
        required=False,
        error_messages={
            "invalid": LONG_DAY_RANGE,
            "min_value": LONG_DAY_RANGE,
            "max_value": LONG_DAY_RANGE,
        },
    )
    long_ride_day = WholeNumberField(
        min_value=0,
        max_value=WEEKDAY_MAX,
        allow_null=True,
        required=False,
        error_messages={
            "invalid": LONG_DAY_RANGE,
            "min_value": LONG_DAY_RANGE,
            "max_value": LONG_DAY_RANGE,
        },
    )
    sport_preferences = SportPreferencesField(
        required=False, error_messages={"null": SPORT_PREFERENCES}
    )
    strength_focus = serializers.ChoiceField(
        choices=StrengthFocus.choices,
        allow_null=True,
        required=False,
        error_messages={"invalid_choice": STRENGTH_FOCUS_CHOICE},
    )
    sports = SportsField(required=False, error_messages={"null": SPORTS_CHOICE})
    stretching = StrictBooleanField(required=False, error_messages={"null": STRETCHING_CHOICE})
    limitations = TextField(max_length=LIMITATIONS_MAX, allow_blank=True, required=False)
    share_limitations_text = StrictBooleanField(
        required=False, error_messages={"null": SHARE_CHOICE}
    )
    intensity_level = serializers.ChoiceField(
        choices=IntensityLevel.choices,
        required=False,
        error_messages={"invalid_choice": LEVEL_CHOICE, "null": LEVEL_CHOICE},
    )
    max_hard_days = _own_limit_field("max_hard_days")
    progression_warning_percent = _own_limit_field("progression_warning_percent")
    progression_error_percent = _own_limit_field("progression_error_percent")
    easy_share_percent = _own_limit_field("easy_share_percent")

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        stored: AvailabilitySettings = self.context.get("settings") or AvailabilitySettings()
        level = attrs.get("intensity_level", stored.intensity_level)
        own = {name: attrs.get(name, getattr(stored, name)) for name in LIMIT_NAMES}
        problems = limit_problems(level, own)
        # The minimum against the budget as both will be after saving: what is sent, and what is
        # stored for the one that is not. The message stands at the field that was sent.
        minimum = attrs.get("min_weekly_minutes", stored.min_weekly_minutes)
        budget = attrs.get("weekly_budget_minutes", stored.weekly_budget_minutes)
        if minimum is not None and budget is not None and minimum > budget:
            if "min_weekly_minutes" in attrs or "weekly_budget_minutes" not in attrs:
                problems["min_weekly_minutes"] = MINIMUM_ABOVE_BUDGET
            else:
                problems["weekly_budget_minutes"] = BUDGET_BELOW_MINIMUM
        if problems:
            raise serializers.ValidationError({name: [text] for name, text in problems.items()})
        return attrs


def availability_data(
    settings: AvailabilitySettings | None,
    weekdays: list[WeekdayMinutes],
    preferences: list[SportPreference] | None = None,
) -> dict[str, Any]:
    """The answer: the seven weekdays (Monday first, 0 where nothing is saved), for each of them
    whether two sessions are allowed and the parts of the day that are open (all of them where
    nothing is saved), the weekly budget, the least the user wants to train in a week, the days a
    week they want to train on and the weekdays of the long run and the long ride (``null`` for
    none of these), what each sport is for the user (role and sessions a week, ``null`` where
    nothing is said), the focus of strength training, the typical week (``null`` for none), the
    sports of the plan (all of them if none was chosen), whether stretching may be added, the
    limitations and whether they may be sent to the coach (off by default), the intensity level
    with the own limits (``null`` for the level's value) and the limits of every level, so that a
    client need not repeat them. No row ids, no owner."""
    minutes = [0] * 7
    double_days = [True] * 7
    time_windows = [list(SLOTS) for _ in range(7)]
    by_sport = {row.sport: row for row in preferences or []}
    for row in weekdays:
        minutes[row.weekday] = row.minutes
        double_days[row.weekday] = row.double_allowed
        time_windows[row.weekday] = row.open_slots
    return {
        "weekdays": minutes,
        "double_days": double_days,
        "time_windows": time_windows,
        "weekly_budget_minutes": settings.weekly_budget_minutes if settings else None,
        "min_weekly_minutes": settings.min_weekly_minutes if settings else None,
        "training_days": settings.training_days if settings else None,
        "long_run_day": settings.long_run_day if settings else None,
        "long_ride_day": settings.long_ride_day if settings else None,
        "typical_weekly_minutes": settings.typical_weekly_minutes if settings else None,
        "sport_preferences": {
            sport: {
                "role": (by_sport[sport].role or None) if sport in by_sport else None,
                "sessions_min": by_sport[sport].sessions_min if sport in by_sport else None,
                "sessions_max": by_sport[sport].sessions_max if sport in by_sport else None,
            }
            for sport in SPORTS
        },
        "strength_focus": (settings.strength_focus or None) if settings else None,
        "sports": effective_sports(settings.sports if settings else None),
        "stretching": settings.stretching if settings else False,
        "limitations": settings.limitations if settings else "",
        "share_limitations_text": settings.share_limitations_text if settings else False,
        "intensity_level": settings.intensity_level if settings else DEFAULT_LEVEL.value,
        **{name: getattr(settings, name) if settings else None for name in LIMIT_NAMES},
        "level_limits": {
            level.value: {name: getattr(limits, name) for name in LIMIT_NAMES}
            for level, limits in LEVEL_LIMITS.items()
        },
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


class LimitationSportsField(serializers.Field[list[str], list[str], list[str], Any]):
    """The sports an entry affects: any of the known ones, each at most once, none is allowed.
    Stored in the order of ``SPORTS``, whatever the order sent."""

    def to_internal_value(self, data: Any) -> list[str]:
        if (
            not isinstance(data, list)
            or not all(isinstance(sport, str) and sport in SPORTS for sport in data)
            or len(set(data)) != len(data)
        ):
            raise serializers.ValidationError(LIMITATION_SPORTS_CHOICE)
        return [sport for sport in SPORTS if sport in data]

    def to_representation(self, value: list[str]) -> list[str]:
        return value


class LimitationSerializer(serializers.ModelSerializer[Limitation]):
    body_part = serializers.ChoiceField(
        choices=BodyPart.choices,
        error_messages={
            "invalid_choice": BODY_PART_CHOICE,
            "required": BODY_PART_CHOICE,
            "null": BODY_PART_CHOICE,
        },
    )
    status = serializers.ChoiceField(
        choices=LimitationStatus.choices,
        required=False,
        error_messages={
            "invalid_choice": LIMITATION_STATUS_CHOICE,
            "null": LIMITATION_STATUS_CHOICE,
        },
    )
    sports = LimitationSportsField(
        required=False, error_messages={"null": LIMITATION_SPORTS_CHOICE}
    )

    class Meta:
        model = Limitation
        fields = ["id", "body_part", "status", "sports"]
        read_only_fields = ["id"]
        validators: list[Any] = []

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        user = self.context["request"].user
        if self.instance is None and Limitation.objects.for_user(user).count() >= MAX_LIMITATIONS:
            raise serializers.ValidationError({"non_field_errors": [TOO_MANY_LIMITATIONS]})
        return attrs

    def to_representation(self, instance: Limitation) -> dict[str, Any]:
        data = dict(super().to_representation(instance))
        data["sports"] = instance.affected_sports
        return data


class FixedSessionSerializer(serializers.ModelSerializer[FixedSession]):
    """A session that repeats every week. The part of the day is ``null`` for none (stored as an
    empty text, as the role of a sport)."""

    weekday = WholeNumberField(
        min_value=0,
        max_value=WEEKDAY_MAX,
        error_messages={
            "invalid": FIXED_WEEKDAY_CHOICE,
            "min_value": FIXED_WEEKDAY_CHOICE,
            "max_value": FIXED_WEEKDAY_CHOICE,
            "required": FIXED_WEEKDAY_CHOICE,
            "null": FIXED_WEEKDAY_CHOICE,
        },
    )
    sport = serializers.ChoiceField(
        choices=SPORTS,
        error_messages={
            "invalid_choice": FIXED_SPORT_CHOICE,
            "required": FIXED_SPORT_CHOICE,
            "null": FIXED_SPORT_CHOICE,
        },
    )
    minutes = WholeNumberField(
        min_value=FIXED_MINUTES_MIN,
        max_value=FIXED_MINUTES_MAX,
        error_messages={
            "invalid": FIXED_MINUTES_RANGE,
            "min_value": FIXED_MINUTES_RANGE,
            "max_value": FIXED_MINUTES_RANGE,
            "required": FIXED_MINUTES_RANGE,
            "null": FIXED_MINUTES_RANGE,
        },
    )
    slot = serializers.ChoiceField(
        choices=SLOTS,
        allow_null=True,
        required=False,
        error_messages={"invalid_choice": FIXED_SLOT_CHOICE},
    )

    class Meta:
        model = FixedSession
        fields = ["id", "weekday", "sport", "minutes", "slot"]
        read_only_fields = ["id"]
        validators: list[Any] = []

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        user = self.context["request"].user
        if (
            self.instance is None
            and FixedSession.objects.for_user(user).count() >= MAX_FIXED_SESSIONS
        ):
            raise serializers.ValidationError({"non_field_errors": [TOO_MANY_FIXED_SESSIONS]})
        if "slot" in attrs:
            attrs["slot"] = attrs["slot"] or ""
        return attrs

    def to_representation(self, instance: FixedSession) -> dict[str, Any]:
        data = dict(super().to_representation(instance))
        data["slot"] = instance.slot or None
        return data
