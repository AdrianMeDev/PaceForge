"""Input checks and the shape of what the athlete API answers.

The answer is built by hand from the user's own values: no row ids, no owner, nothing that the
browser did not ask for. Values the user has not got are ``null``.
"""

import dataclasses
from typing import Any

from rest_framework import serializers

from accounts.models import User
from integrations import services as integrations
from integrations.models import ProviderConnection

from .models import (
    RULES,
    TRAINING_YEARS_MAX,
    YEARS_SPORTS,
    AthleteProfile,
    Equipment,
    Sex,
    StrengthExperience,
    validate_time_zone,
)
from .thresholds import Value, all_candidates
from .zones import ZoneSet, heart_rate_zones, pace_zones, power_zones

_TIMESTAMP = serializers.DateTimeField()


NOTHING_TO_CHANGE = "Send at least one field to change."
TRAINING_YEARS = (
    f"Send an object with any of {', '.join(YEARS_SPORTS)}, each a whole number of years between "
    f"0 and {TRAINING_YEARS_MAX} or null."
)
EQUIPMENT_CHOICE = f"Choose any of: {', '.join(Equipment.values)}, or none."


class NumberField(serializers.FloatField):
    """A JSON number. Text that looks like one ("250") and true/false are not numbers."""

    def to_internal_value(self, data: Any) -> float:
        if isinstance(data, bool) or not isinstance(data, int | float):
            self.fail("invalid")
        return super().to_internal_value(data)


class WholeNumberField(serializers.IntegerField):
    """A JSON integer. Text, fractions and true/false are not integers."""

    def to_internal_value(self, data: Any) -> int:
        if isinstance(data, bool) or not isinstance(data, int):
            self.fail("invalid")
        return super().to_internal_value(data)


class TrainingYearsField(serializers.Field[dict[str, int | None], Any, Any, Any]):
    """Years of training by sport: an object with any of the sports, each a whole number or
    ``null`` (not said). A sport that is left out stays as it is."""

    def to_internal_value(self, data: Any) -> dict[str, int | None]:
        if not isinstance(data, dict) or not set(data) <= set(YEARS_SPORTS):
            raise serializers.ValidationError(TRAINING_YEARS)
        for years in data.values():
            if years is not None and (
                isinstance(years, bool)
                or not isinstance(years, int)
                or not 0 <= years <= TRAINING_YEARS_MAX
            ):
                raise serializers.ValidationError(TRAINING_YEARS)
        return dict(data)

    def to_representation(self, value: Any) -> Any:
        return value


class EquipmentField(serializers.Field[list[str], Any, Any, Any]):
    """The equipment for strength training: any of the known ones, each at most once, none is
    allowed. Stored in the order of ``Equipment``, whatever the order sent."""

    def to_internal_value(self, data: Any) -> list[str]:
        if (
            not isinstance(data, list)
            or not all(isinstance(item, str) and item in Equipment.values for item in data)
            or len(set(data)) != len(data)
        ):
            raise serializers.ValidationError(EQUIPMENT_CHOICE)
        return [item for item in Equipment.values if item in data]

    def to_representation(self, value: Any) -> Any:
        return value


class AthleteInput(serializers.Serializer):
    """What may be changed on the profile. Every field is optional, a missing one is left as it
    is and ``null`` clears one; at least one has to be there."""

    # Strict: the name must be exactly one from the database, so no trimming of white space.
    timezone = serializers.CharField(
        max_length=64,
        allow_blank=True,
        trim_whitespace=False,
        validators=[validate_time_zone],
        required=False,
    )
    birth_year = WholeNumberField(allow_null=True, required=False)
    sex = serializers.ChoiceField(choices=Sex.choices, allow_null=True, required=False)
    weight_kg = NumberField(allow_null=True, required=False)
    resting_hr = WholeNumberField(allow_null=True, required=False)
    training_years = TrainingYearsField(required=False)
    strength_experience = serializers.ChoiceField(
        choices=StrengthExperience.choices, allow_null=True, required=False
    )
    strength_equipment = EquipmentField(required=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if not attrs:
            raise serializers.ValidationError({"non_field_errors": [NOTHING_TO_CHANGE]})
        return attrs


class ThresholdInput(serializers.Serializer):
    value = NumberField()


def athlete_data(user: User, profile: AthleteProfile | None) -> dict[str, Any]:
    """The whole profile of ``user``: time zone, thresholds with their sources, and the zones."""
    found = all_candidates(user)
    connection = integrations.get_connection(user)
    sports: dict[str, Any] = {}
    for sport in ("ride", "run"):
        metrics = [metric for (s, metric) in RULES if s == sport]
        sports[sport] = {
            "thresholds": {
                metric: _threshold(found.get((sport, metric), [])) for metric in metrics
            },
            "zones": _zones(sport, found),
        }
    return {
        "timezone": profile.timezone if profile else "",
        **_body_and_training(profile),
        "intervals": {
            "connected": connection is not None
            and connection.status == ProviderConnection.Status.CONNECTED,
            "synced_at": _time(profile.intervals_synced_at) if profile else None,
        },
        "sports": sports,
    }


def _body_and_training(profile: AthleteProfile | None) -> dict[str, Any]:
    """The body and training data; ``null`` for what was not said (no equipment is ``[]``)."""
    if profile is None:
        profile = AthleteProfile()
    return {
        "birth_year": profile.birth_year,
        "sex": profile.sex or None,
        "weight_kg": profile.weight_kg,
        "resting_hr": profile.resting_hr,
        "training_years": {sport: getattr(profile, f"years_{sport}") for sport in YEARS_SPORTS},
        "strength_experience": profile.strength_experience or None,
        "strength_equipment": profile.equipment,
    }


def _threshold(values: list[Value]) -> dict[str, Any]:
    return {
        "effective": _value(values[0]) if values else None,
        "candidates": [_value(value) for value in values],
    }


def _value(value: Value) -> dict[str, Any]:
    return {
        "value": value.value,
        "source": value.source,
        "basis": value.basis,
        "updated_at": _time(value.updated_at),
    }


def _zones(sport: str, found: dict[tuple[str, str], list[Value]]) -> dict[str, Any]:
    def number(metric: str) -> float | None:
        values = found.get((sport, metric))
        return values[0].value if values else None

    heart_rate = heart_rate_zones(lthr=number("lthr"), max_hr=number("max_hr"))
    if sport == "ride":
        return {"power": _zone_set(power_zones(number("ftp"))), "heart_rate": _zone_set(heart_rate)}
    return {
        "pace": _zone_set(pace_zones(number("threshold_pace"))),
        "heart_rate": _zone_set(heart_rate),
    }


def _zone_set(zone_set: ZoneSet | None) -> dict[str, Any] | None:
    return dataclasses.asdict(zone_set) if zone_set else None


def _time(moment: Any) -> str | None:
    return _TIMESTAMP.to_representation(moment) if moment else None
