import datetime as dt
import unicodedata
from typing import Any

from django.utils import timezone
from rest_framework import serializers

from accounts.models import User
from athletes.serializers import NumberField
from goals.services import time_zone_of

from .load import load_of
from .models import NOTES_MAX, RPE_MAX, Activity

SUMMARY_FIELDS = [
    "id",
    "source",
    "sport",
    "source_sport",
    "start_time",
    "elapsed_seconds",
    "timer_seconds",
    "distance_m",
    "avg_heart_rate",
    "max_heart_rate",
    "avg_power_w",
    "total_ascent_m",
    "calories",
    "manufacturer",
    "rpe",
    "notes",
    "load",
    "created_at",
]


class ActivitySerializer(serializers.ModelSerializer[Activity]):
    """The summary of an activity. Neither the owner, the file hash nor the file itself is part of
    it: the file holds the whole GPS track and is never returned. ``load`` is the estimate from the
    duration and the RPE (see ``activities.load``), ``None`` without either."""

    load = serializers.SerializerMethodField()

    def get_load(self, activity: Activity) -> int | None:
        return load_of(activity)

    class Meta:
        model = Activity
        fields = SUMMARY_FIELDS
        read_only_fields = fields


class ActivityDetailSerializer(ActivitySerializer):
    class Meta(ActivitySerializer.Meta):
        fields = [*SUMMARY_FIELDS, "laps"]
        read_only_fields = fields


DURATION_MAX_MINUTES = 1440  # a day
DISTANCE_MAX_KM = 1000
EARLIEST = dt.date(2000, 1, 1)
# What the form may say, in fixed words: nothing of the input is repeated in an answer.
NOT_A_SPORT = "Choose one of the sports."
IN_THE_FUTURE = "The session cannot start in the future."
TOO_OLD = f"Choose a date from {EARLIEST.year} on."
CONTROL_CHARACTERS = "Must not contain control characters."
ONLY_THE_RATING = "Only the rating (rpe) and the note (notes) can be changed."


class WholeNumberField(serializers.IntegerField):
    """A JSON integer. Text such as "60", fractions and true/false are not integers."""

    def to_internal_value(self, data: Any) -> int:
        if isinstance(data, bool) or not isinstance(data, int):
            self.fail("invalid")
        return super().to_internal_value(data)


class TextField(serializers.CharField):
    """Text. A number or a list is not turned into text: that would hide a client's mistake."""

    def to_internal_value(self, data: Any) -> str:
        if not isinstance(data, str):
            self.fail("invalid")
        return super().to_internal_value(data)


def checked_note(value: str) -> str:
    """A note may have several lines; nothing else that is invisible or reorders text."""
    if any(
        unicodedata.category(char) in {"Cc", "Cf", "Zl", "Zp"} and char != "\n" for char in value
    ):
        raise serializers.ValidationError(CONTROL_CHARACTERS)
    return value


class ManualActivitySerializer(serializers.Serializer[Any]):
    """A session the user enters by hand. The date and the time are those on the user's wall clock;
    they are turned into the moment they mean in the time zone of the profile."""

    sport = serializers.ChoiceField(
        choices=Activity.Sport.choices, error_messages={"invalid_choice": NOT_A_SPORT}
    )
    date = serializers.DateField()
    time = serializers.TimeField(input_formats=["%H:%M"])
    duration_minutes = WholeNumberField(min_value=1, max_value=DURATION_MAX_MINUTES)
    distance_km = NumberField(
        min_value=0, max_value=DISTANCE_MAX_KM, allow_null=True, required=False
    )
    rpe = WholeNumberField(min_value=1, max_value=RPE_MAX, allow_null=True, required=False)
    notes = TextField(max_length=NOTES_MAX, allow_blank=True, required=False)

    def validate_date(self, value: dt.date) -> dt.date:
        if value < EARLIEST:
            raise serializers.ValidationError(TOO_OLD)
        return value

    def validate_notes(self, value: str) -> str:
        return checked_note(value)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        user = self.context["user"]
        start = self.start_of(user, attrs["date"], attrs["time"])
        if start > timezone.now():
            raise serializers.ValidationError({"date": [IN_THE_FUTURE]})
        attrs["start"] = start
        return attrs

    @staticmethod
    def start_of(user: User, day: dt.date, clock: dt.time) -> dt.datetime:
        """The moment ``day`` and ``clock`` mean on the user's wall clock, in UTC."""
        return dt.datetime.combine(day, clock, tzinfo=time_zone_of(user)).astimezone(dt.UTC)


class ActivityRatingSerializer(serializers.Serializer[Any]):
    """What the user may change about an activity after the fact: how hard it felt and a note.
    Nothing else is ever changed, so any other field is refused rather than ignored (a client
    that sends one has a mistake worth showing). A ``null`` rpe and an empty ``notes`` clear them.
    """

    rpe = WholeNumberField(min_value=1, max_value=RPE_MAX, allow_null=True, required=False)
    notes = TextField(max_length=NOTES_MAX, allow_blank=True, required=False)

    def validate_notes(self, value: str) -> str:
        return checked_note(value)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        sent = self.initial_data
        if not attrs or not isinstance(sent, dict) or set(sent) - set(self.fields):
            raise serializers.ValidationError(ONLY_THE_RATING)
        return attrs

    def update(self, instance: Activity, validated_data: dict[str, Any]) -> Activity:
        for name, value in validated_data.items():
            setattr(instance, name, value)
        instance.save(update_fields=list(validated_data))
        return instance
