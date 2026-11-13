"""Importing an uploaded activity file: check, parse, refuse duplicates, store."""

import hashlib

from django.conf import settings
from django.db import IntegrityError, transaction

from accounts.models import User

from .models import Activity, ActivityFile
from .parsing import ParsedActivity, parse_activity_file


class FileTooLargeError(Exception):
    """The file is bigger than ``ACTIVITY_UPLOAD_MAX_BYTES``. Nothing of it was read."""


class DuplicateActivityError(Exception):
    """The user already has this file or this activity. Carries the id of the existing one."""

    def __init__(self, existing_id: object) -> None:
        super().__init__("This activity has already been imported.")
        self.existing_id = existing_id


def import_activity(user: User, data: bytes) -> Activity:
    """Store the activity of ``data`` for ``user``, together with the original file.

    Raises ``FileTooLargeError``, ``ActivityFileError`` (from the parsers) or
    ``DuplicateActivityError``; in each case nothing is stored.
    """
    if len(data) > settings.ACTIVITY_UPLOAD_MAX_BYTES:
        raise FileTooLargeError("The file is too large.")

    parsed = parse_activity_file(data)
    source_hash = hashlib.sha256(data).hexdigest()

    existing = _find_duplicate(user, source_hash, parsed)
    if existing is not None:
        raise DuplicateActivityError(existing.pk)

    try:
        with transaction.atomic():
            activity = Activity.objects.create(
                owner=user, source_hash=source_hash, **_fields(parsed)
            )
            ActivityFile.for_activity(activity, data).save()
    except IntegrityError:
        # Another request stored the same activity between the check above and the insert.
        existing = _find_duplicate(user, source_hash, parsed)
        if existing is None:
            raise
        raise DuplicateActivityError(existing.pk) from None
    return activity


def _find_duplicate(user: User, source_hash: str, parsed: ParsedActivity) -> Activity | None:
    """The same file, or the same run exported in another format (same start and sport)."""
    own = Activity.objects.filter(owner=user)
    return (
        own.filter(source_hash=source_hash).first()
        or own.filter(start_time=parsed.start_time, sport=parsed.sport).first()
    )


def _fields(parsed: ParsedActivity) -> dict[str, object]:
    return {
        "source": parsed.source,
        "sport": parsed.sport,
        "source_sport": parsed.source_sport,
        "start_time": parsed.start_time,
        "elapsed_seconds": parsed.elapsed_seconds,
        "timer_seconds": parsed.timer_seconds,
        "distance_m": parsed.distance_m,
        "avg_heart_rate": parsed.avg_heart_rate,
        "max_heart_rate": parsed.max_heart_rate,
        "avg_power_w": parsed.avg_power_w,
        "total_ascent_m": parsed.total_ascent_m,
        "calories": parsed.calories,
        "manufacturer": parsed.manufacturer,
        "laps": [
            {
                "start_time": lap.start_time.isoformat() if lap.start_time else None,
                "elapsed_seconds": lap.elapsed_seconds,
                "distance_m": lap.distance_m,
                "avg_heart_rate": lap.avg_heart_rate,
                "max_heart_rate": lap.max_heart_rate,
            }
            for lap in parsed.laps
        ],
    }
