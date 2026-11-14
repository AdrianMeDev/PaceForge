"""Rows for the tests of the week review: a confirmed plan and activities in the week of
``MONDAY``, with the clock of the tests fixed on ``NOW``."""

from datetime import UTC, date, datetime, timedelta
from typing import Any

from accounts.models import User
from activities.models import Activity
from planning.models import PlannedWorkout, WeeklyPlan

# A Saturday; its week starts on Monday the 9th.
NOW = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)
MONDAY = date(2026, 11, 9)
assert MONDAY.weekday() == 0


def make_plan(
    owner: User, monday: date = MONDAY, status: str = "confirmed", workouts: int = 0
) -> WeeklyPlan:
    stamp = NOW if status in ("confirmed", "superseded") else None
    version = WeeklyPlan.objects.filter(owner=owner, week_start=monday).count() + 1
    plan = WeeklyPlan.objects.create(
        owner=owner, week_start=monday, version=version, status="draft"
    )
    PlannedWorkout.objects.bulk_create(
        [
            PlannedWorkout(
                owner=owner,
                plan=plan,
                day=monday + timedelta(days=n % 7),
                position=n // 7,
                sport="running",
                title=f"Run {n}",
                goal="endurance",
                duration_minutes=60,
            )
            for n in range(workouts)
        ]
    )
    WeeklyPlan.objects.filter(pk=plan.pk).update(status=status, confirmed_at=stamp)
    plan.refresh_from_db()
    return plan


def make_activity(owner: User, start: str, **fields: Any) -> Activity:
    values: dict[str, Any] = {
        "source": "manual",
        "sport": "running",
        "timer_seconds": 3600.0,
        **fields,
    }
    return Activity.objects.create(
        owner=owner, start_time=datetime.fromisoformat(start).replace(tzinfo=UTC), **values
    )
