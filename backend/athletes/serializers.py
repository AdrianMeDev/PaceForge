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

from .models import RULES, AthleteProfile, validate_time_zone
from .thresholds import Value, all_candidates
from .zones import ZoneSet, heart_rate_zones, pace_zones, power_zones

_TIMESTAMP = serializers.DateTimeField()


class TimezoneInput(serializers.Serializer):
    # Strict: the name must be exactly one from the database, so no trimming of white space.
    timezone = serializers.CharField(
        max_length=64, allow_blank=True, trim_whitespace=False, validators=[validate_time_zone]
    )


class NumberField(serializers.FloatField):
    """A JSON number. Text that looks like one ("250") and true/false are not numbers."""

    def to_internal_value(self, data: Any) -> float:
        if isinstance(data, bool) or not isinstance(data, int | float):
            self.fail("invalid")
        return super().to_internal_value(data)


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
        "intervals": {
            "connected": connection is not None
            and connection.status == ProviderConnection.Status.CONNECTED,
            "synced_at": _time(profile.intervals_synced_at) if profile else None,
        },
        "sports": sports,
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
