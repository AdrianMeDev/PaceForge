"""Importing a user's recent activities from their Intervals.icu connection.

Only the user's own connection and key are used, and only new activities are written: one that
was synced before (same Intervals.icu id), or that is the same session as an uploaded file or a
manual entry (see ``duplicates``), is skipped. Strava activities cannot be read through the API
and are skipped by the client.
"""

from contextlib import suppress
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction

from accounts.models import User
from athletes.estimates import refresh_estimates_safely
from goals.services import today_of
from integrations import services as integrations
from integrations.intervals import (
    ActivityBatch,
    IntervalsActivity,
    IntervalsError,
    IntervalsUnavailableError,
    InvalidKeyError,
)
from integrations.models import ProviderConnection

from .duplicates import duration_of, find_duplicate
from .models import Activity

SyncError = ProviderConnection.SyncError


@dataclass(frozen=True)
class SyncCounts:
    imported: int
    skipped_duplicates: int
    skipped_strava: int
    skipped_invalid: int


def sync_from_intervals(user: User) -> SyncCounts:
    """Import the activities of the last ``INTERVALS_SYNC_WEEKS`` weeks (up to today in the user's
    time zone) and record the sync on the connection.

    Raises ``NotConnectedError`` (nothing is recorded) and the errors of the client
    (``InvalidKeyError``, ``IntervalsUnavailableError``, ``UnexpectedResponseError``); then nothing
    is imported, the error's fixed code is recorded and the time of the last sync stays as it was.
    """
    newest = today_of(user)
    oldest = newest - timedelta(weeks=settings.INTERVALS_SYNC_WEEKS)
    try:
        batch = integrations.with_client(user, lambda client: client.get_activities(oldest, newest))
    except IntervalsError as error:
        _record(user, _error_code(error))
        raise

    imported = _store(user, batch.activities)
    if imported:
        refresh_estimates_safely(user)
    _record(user, SyncError.NONE)
    return _counts(batch, imported)


def _store(user: User, activities: tuple[IntervalsActivity, ...]) -> int:
    """Store the activities the user does not have yet; returns how many were stored."""
    known = set(
        Activity.objects.for_user(user)
        .filter(
            source=Activity.Source.INTERVALS_ICU,
            external_id__in=[activity.external_id for activity in activities],
        )
        .values_list("external_id", flat=True)
    )
    imported = 0
    for activity in activities:
        if activity.external_id in known:
            continue
        seconds = duration_of(activity.timer_seconds, activity.elapsed_seconds)
        if find_duplicate(user, activity.sport, activity.start_time, seconds) is not None:
            continue
        try:
            with transaction.atomic():
                Activity.objects.create(owner=user, best_efforts={}, **_fields(activity))
        except IntegrityError:
            # A second sync stored it between the check above and the insert.
            continue
        imported += 1
    return imported


def _counts(batch: ActivityBatch, imported: int) -> SyncCounts:
    return SyncCounts(
        imported=imported,
        skipped_duplicates=len(batch.activities) - imported,
        skipped_strava=batch.skipped_strava,
        skipped_invalid=batch.skipped_invalid,
    )


def _fields(activity: IntervalsActivity) -> dict[str, object]:
    return {
        "source": Activity.Source.INTERVALS_ICU,
        "external_id": activity.external_id,
        "sport": activity.sport,
        "source_sport": activity.source_sport,
        "start_time": activity.start_time,
        "elapsed_seconds": activity.elapsed_seconds,
        "timer_seconds": activity.timer_seconds,
        "distance_m": activity.distance_m,
        "training_load": activity.training_load,
        "avg_heart_rate": activity.avg_heart_rate,
        "max_heart_rate": activity.max_heart_rate,
        "avg_pace_s_per_km": activity.avg_pace_s_per_km,
        "avg_power_w": activity.avg_power_w,
        "total_ascent_m": activity.total_ascent_m,
        "calories": activity.calories,
    }


def _error_code(error: IntervalsError) -> str:
    if isinstance(error, InvalidKeyError):
        return SyncError.INVALID_KEY
    if isinstance(error, IntervalsUnavailableError):
        return SyncError.UNAVAILABLE
    return SyncError.UNEXPECTED


def _record(user: User, error: str) -> None:
    # The connection was removed while the sync ran: there is nothing left to record on.
    with suppress(integrations.NotConnectedError):
        integrations.record_sync_result(user, error=error)
