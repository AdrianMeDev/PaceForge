"""The export of everything PaceForge stores about one user (data portability).

``build_user_export`` reads every personal model through ``for_user()``, so nothing of another
user can get in. What never goes in: the password hash, the second factor (secret and recovery
codes), API keys and anything else that is a credential, the uploaded activity files (they hold
the whole track) and the fields that only serve the import (``source_hash``, ``external_id``,
``best_efforts``). Integrations use an explicit metadata allowlist. In other sections a new
field is exported by default; a new secret must be added to the ``exclude`` of its section or
be an ``EncryptedTextField``, which is always left out.
"""

import json
from collections.abc import Iterable
from typing import Any

from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.utils import timezone

from accounts.models import User
from activities.models import Activity
from athletes.models import AthleteProfile, BestTime, ThresholdValue
from availability.models import (
    AvailabilitySettings,
    FixedSession,
    Limitation,
    SportPreference,
    UnavailablePeriod,
    WeekdayMinutes,
)
from chat.models import ChatMessage
from coach.models import AIModelPrice, AIProviderConfiguration, AIUsageRecord
from core.fields import EncryptedTextField
from goals.models import Goal
from integrations.models import ProviderConnection
from jobs.models import JobRun, JobSettings
from planning.models import PlannedWorkout, WeeklyPlan
from reviews.models import WeekComment, WeekFeedback, WorkoutReview
from season.models import SeasonPlanVersion
from wellness.models import DailyWellness

# Bump when a section changes in a way that a reader of the file has to know about.
EXPORT_VERSION = 1

INTEGRATION_EXPORT_FIELDS = (
    "provider",
    "athlete_id",
    "status",
    "connected_at",
    "last_checked_at",
    "last_sync_at",
    "last_sync_error",
)

Row = dict[str, Any]


def _integration_row(connection: ProviderConnection) -> Row:
    """Copy only approved connection metadata, even when new plain fields are added."""
    return {name: getattr(connection, name) for name in INTEGRATION_EXPORT_FIELDS}


def _row(instance: models.Model, exclude: Iterable[str] = ()) -> Row:
    """The columns of one record. The owner is the account itself and is left out; a relation is
    given as the id of the other record. Credentials (encrypted fields) are never copied."""
    skip = {"owner", *exclude}
    row: Row = {}
    for field in instance._meta.concrete_fields:
        if field.name in skip or isinstance(field, EncryptedTextField):
            continue
        if field.primary_key and not isinstance(field, models.UUIDField):
            continue  # an internal counter that means nothing outside the database
        row[field.attname] = field.value_from_object(instance)
    return row


def _rows[M: models.Model](queryset: models.QuerySet[M], exclude: Iterable[str] = ()) -> list[Row]:
    ordering = queryset.model._meta.ordering or ["pk"]
    return [_row(item, exclude) for item in queryset.order_by(*ordering)]


def _one(instance: models.Model | None, exclude: Iterable[str] = ()) -> Row | None:
    return None if instance is None else _row(instance, exclude)


def _plans(user: User) -> list[Row]:
    workouts: dict[Any, list[Row]] = {}
    workout_rows = PlannedWorkout.objects.for_user(user).order_by("day", "position", "id")
    for workout in workout_rows:
        workouts.setdefault(workout.plan_id, []).append(_row(workout, exclude=("plan",)))
    plans = WeeklyPlan.objects.for_user(user).order_by("week_start", "version")
    return [{**_row(plan), "workouts": workouts.get(plan.pk, [])} for plan in plans]


def build_user_export(user: User) -> dict[str, Any]:
    """Everything stored about ``user`` as plain data that ``json.dumps`` accepts."""
    provider = AIProviderConfiguration.objects.for_user(user).first()
    coach_provider = _one(provider)
    if coach_provider is not None:
        coach_provider["has_api_key"] = bool(provider and provider.api_key)

    data: dict[str, Any] = {
        "version": EXPORT_VERSION,
        "exported_at": timezone.now(),
        "account": {
            "email": user.email,
            "display_name": user.display_name,
            "date_joined": user.date_joined,
        },
        "profile": {
            "athlete": _one(AthleteProfile.objects.for_user(user).first()),
            "thresholds": _rows(ThresholdValue.objects.for_user(user)),
            "best_times": _rows(BestTime.objects.for_user(user)),
        },
        "availability": {
            "settings": _one(AvailabilitySettings.objects.for_user(user).first()),
            "weekdays": _rows(WeekdayMinutes.objects.for_user(user)),
            "sport_preferences": _rows(SportPreference.objects.for_user(user)),
            "fixed_sessions": _rows(FixedSession.objects.for_user(user)),
            "unavailable_periods": _rows(UnavailablePeriod.objects.for_user(user)),
            "limitations": _rows(Limitation.objects.for_user(user)),
        },
        "goals": _rows(Goal.objects.for_user(user)),
        "activities": _rows(
            Activity.objects.for_user(user), exclude=("source_hash", "external_id", "best_efforts")
        ),
        "wellness": _rows(DailyWellness.objects.for_user(user)),
        "plans": {
            "season": _rows(SeasonPlanVersion.objects.for_user(user)),
            "weeks": _plans(user),
        },
        "reviews": {
            "workouts": _rows(WorkoutReview.objects.for_user(user)),
            "week_feedback": _rows(WeekFeedback.objects.for_user(user)),
            "week_comments": _rows(WeekComment.objects.for_user(user)),
        },
        "chat": _rows(ChatMessage.objects.for_user(user)),
        "coach": {
            "provider": coach_provider,
            "usage": _rows(AIUsageRecord.objects.for_user(user)),
            "prices": _rows(AIModelPrice.objects.for_user(user)),
        },
        "integrations": [
            _integration_row(connection)
            for connection in ProviderConnection.objects.for_user(user).order_by("pk")
        ],
        "automation": {
            "settings": _one(JobSettings.objects.for_user(user).first()),
            "runs": _rows(JobRun.objects.for_user(user)),
        },
    }
    # One pass through the JSON encoder turns dates, UUIDs and decimals into text.
    return json.loads(json.dumps(data, cls=DjangoJSONEncoder))
