"""Input checks and the shape of what the jobs API answers.

Nothing of another user is ever included, and a run never holds free text from a provider:
``code`` is a fixed word (or empty) and ``counts`` holds numbers only.
"""

from typing import Any

from rest_framework import serializers

from .models import JobRun, JobSettings
from .services import counts_or_default

_TIME = serializers.DateTimeField()

NOT_A_BOOLEAN = "Must be true or false."
ONLY_THESE_FIELDS = "Only the fields of this form can be sent."
NOTHING_TO_CHANGE = "Send at least one field to change."


class FlagField(serializers.BooleanField):
    """A JSON true or false. Text such as "true" and numbers are not flags."""

    default_error_messages = {"invalid": NOT_A_BOOLEAN}

    def to_internal_value(self, data: Any) -> bool:
        if not isinstance(data, bool):
            self.fail("invalid")
        return data


class JobSettingsInput(serializers.Serializer[Any]):
    """Which background jobs the user lets run; every field is optional."""

    sync = FlagField(required=False)
    week_review = FlagField(required=False)
    week_draft = FlagField(required=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        sent = self.initial_data
        if not isinstance(sent, dict) or set(sent) - set(self.fields):
            raise serializers.ValidationError(ONLY_THESE_FIELDS)
        if not attrs:
            raise serializers.ValidationError({"non_field_errors": [NOTHING_TO_CHANGE]})
        return attrs


def settings_data(settings: JobSettings) -> dict[str, bool]:
    """The user's job toggles."""
    return {
        "sync": settings.sync,
        "week_review": settings.week_review,
        "week_draft": settings.week_draft,
    }


def run_data(run: JobRun) -> dict[str, Any]:
    """One logged job attempt, for the athlete's job log."""
    return {
        "id": str(run.pk),
        "job": run.job,
        "week_start": run.week_start.isoformat() if run.week_start is not None else None,
        "started_at": _TIME.to_representation(run.started_at),
        "finished_at": _TIME.to_representation(run.finished_at),
        "outcome": run.outcome,
        "code": run.code,
        "counts": counts_or_default(run.counts),
    }
