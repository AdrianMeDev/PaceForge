"""Storing a user's daily wellness from Intervals.icu.

The rows are keyed by ``(owner, day)``; the same day read again updates the row when a metric
changed and otherwise leaves it (and its ``updated_at``) untouched, so a repeated sync reports no
change. Entries are always the user's own: ``store_wellness`` writes only for the user it is given
and never reads another user's rows.
"""

from accounts.models import User
from integrations.intervals import IntervalsWellness

from .models import DailyWellness

# The four metrics written to a row. Their order is only for the update defaults below.
METRICS = ("sleep_minutes", "hrv", "resting_hr", "weight_kg")


def store_wellness(
    user: User, entries: list[IntervalsWellness] | tuple[IntervalsWellness, ...]
) -> int:
    """Upsert the given entries for ``user`` by day; return how many rows were created or changed.

    A day already present is updated only when at least one metric value differs; an unchanged day
    is left alone (its ``updated_at`` stays). Rows for other users are never touched.
    """
    changed = 0
    existing = {
        row.day: row
        for row in DailyWellness.objects.for_user(user).filter(
            day__in=[entry.day for entry in entries]
        )
    }
    for entry in entries:
        row = existing.get(entry.day)
        if row is None:
            DailyWellness.objects.create(owner=user, day=entry.day, **_metrics(entry))
            changed += 1
            continue
        updates = _metric_changes(row, entry)
        if not updates:
            continue
        for field, value in updates.items():
            setattr(row, field, value)
        row.save(update_fields=[*updates.keys(), "updated_at"])
        changed += 1
    return changed


def _metrics(entry: IntervalsWellness) -> dict[str, int | float | None]:
    return {field: getattr(entry, field) for field in METRICS}


def _metric_changes(row: DailyWellness, entry: IntervalsWellness) -> dict[str, int | float | None]:
    """The metric values of ``entry`` that differ from ``row`` (by field name)."""
    changes: dict[str, int | float | None] = {}
    for field in METRICS:
        stored = getattr(row, field)
        incoming = getattr(entry, field)
        if stored != incoming:
            changes[field] = incoming
    return changes
