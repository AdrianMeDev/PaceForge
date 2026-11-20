"""Linked exports keep the workout's owner even through direct database writes."""

from datetime import date
from typing import Any

import pytest
from django.db import IntegrityError, transaction

from accounts.models import User
from planning.models import PlannedWorkout, WeeklyPlan, WorkoutExport

MONDAY = date(2027, 7, 12)
pytestmark = pytest.mark.django_db


@pytest.fixture
def workouts() -> tuple[PlannedWorkout, PlannedWorkout]:
    rows = []
    for email in ("alice@example.com", "bob@example.com"):
        owner = User.objects.create_user(email)
        plan = WeeklyPlan.objects.create(owner=owner, week_start=MONDAY)
        rows.append(
            PlannedWorkout.objects.create(
                owner=owner,
                plan=plan,
                day=MONDAY,
                sport="running",
                title="Run",
                goal="endurance",
                duration_minutes=60,
            )
        )
    return rows[0], rows[1]


def fields(source: PlannedWorkout, **changes: Any) -> dict[str, Any]:
    return {
        "owner_id": source.owner_id,
        "workout": source,
        "week_start": MONDAY,
        "external_id": "paceforge-test",
        "event_id": 123,
        "status": "synced",
        **changes,
    }


@pytest.mark.parametrize("owner_index", [0, 1])
@pytest.mark.parametrize(
    "method", ["create", "save", "save_owner", "bulk_create", "bulk_update", "relink", "owner"]
)
def test_cross_owner_export_writes_are_atomic(
    workouts: tuple[PlannedWorkout, PlannedWorkout], owner_index: int, method: str
) -> None:
    mine, theirs = workouts[owner_index], workouts[1 - owner_index]
    existing = WorkoutExport.objects.create(**fields(mine))
    with pytest.raises(IntegrityError, match="planning_export_workout_owner"), transaction.atomic():
        if method == "create":
            WorkoutExport.objects.create(**fields(mine, workout=theirs, external_id="invalid"))
        elif method == "save":
            existing.workout = theirs
            existing.save()
        elif method == "save_owner":
            existing.owner_id = theirs.owner_id
            existing.save(update_fields=["owner"])
        elif method == "bulk_create":
            WorkoutExport.objects.bulk_create(
                [
                    WorkoutExport(**fields(mine, external_id="valid")),
                    WorkoutExport(**fields(mine, workout=theirs, external_id="invalid")),
                ]
            )
        elif method == "bulk_update":
            existing.workout = theirs
            WorkoutExport.objects.bulk_update([existing], ["workout"])
        elif method == "relink":
            WorkoutExport.objects.filter(pk=existing.pk).update(workout=theirs)
        else:
            WorkoutExport.objects.filter(pk=existing.pk).update(owner_id=theirs.owner_id)
    existing.refresh_from_db()
    assert WorkoutExport.objects.count() == 1
    assert (existing.owner_id, existing.workout_id, existing.event_id) == (
        mine.owner_id,
        mine.pk,
        123,
    )


@pytest.mark.parametrize("owner_index", [0, 1])
@pytest.mark.parametrize("method", ["save", "update", "bulk_update"])
def test_workout_owner_changes_cannot_strand_exports(
    workouts: tuple[PlannedWorkout, PlannedWorkout], owner_index: int, method: str
) -> None:
    mine, theirs = workouts[owner_index], workouts[1 - owner_index]
    export = WorkoutExport.objects.create(**fields(mine))
    # Move to a matching plan as well, so the workout-plan guard accepts the change.
    with pytest.raises(IntegrityError, match="planning_export_workout_owner"), transaction.atomic():
        if method == "update":
            PlannedWorkout.objects.filter(pk=mine.pk).update(
                owner_id=theirs.owner_id, plan=theirs.plan, position=1
            )
        else:
            mine.owner_id = theirs.owner_id
            mine.plan = theirs.plan
            mine.position = 1
            if method == "save":
                mine.save()
            else:
                PlannedWorkout.objects.bulk_update([mine], ["owner", "plan", "position"])
    mine.refresh_from_db()
    export.refresh_from_db()
    assert mine.owner_id == export.owner_id
    assert export.workout_id == mine.pk
    assert mine.plan_id != theirs.plan_id


def test_same_owner_relink_and_push_state_updates_keep_the_event(
    workouts: tuple[PlannedWorkout, PlannedWorkout],
) -> None:
    mine, _ = workouts
    export = WorkoutExport.objects.create(**fields(mine))
    newer = WeeklyPlan.objects.create(owner=mine.owner, week_start=MONDAY, version=2)
    replacement = PlannedWorkout.objects.create(
        owner=mine.owner,
        plan=newer,
        day=MONDAY,
        sport="running",
        title="Revised run",
        goal="endurance",
        duration_minutes=45,
        lineage=mine.lineage,
    )
    export.workout = replacement
    export.status = "failed"
    export.error_code = "unavailable"
    export.save()
    WorkoutExport.objects.filter(pk=export.pk).update(status="synced", error_code="")
    export.refresh_from_db()
    assert (export.workout_id, export.event_id, export.status) == (replacement.pk, 123, "synced")


@pytest.mark.parametrize("cleanup", ["detach", "workout", "plan"])
def test_null_links_and_set_null_cleanup_keep_external_event_records(
    workouts: tuple[PlannedWorkout, PlannedWorkout], cleanup: str
) -> None:
    mine, theirs = workouts
    export = WorkoutExport.objects.create(**fields(mine))
    if cleanup == "detach":
        WorkoutExport.objects.filter(pk=export.pk).update(workout=None)
    elif cleanup == "workout":
        mine.delete()
    else:
        mine.plan.delete()
    export.refresh_from_db()
    assert export.workout_id is None
    assert (export.external_id, export.event_id, export.status) == ("paceforge-test", 123, "synced")
    # Detached records have no workout owner to match, and may be created or updated.
    export.owner_id = theirs.owner_id
    export.save()
    detached = WorkoutExport.objects.create(**fields(mine, workout=None, external_id="detached"))
    assert detached.workout_id is None


def test_detached_export_cannot_be_attached_to_another_owner(
    workouts: tuple[PlannedWorkout, PlannedWorkout],
) -> None:
    mine, theirs = workouts
    export = WorkoutExport.objects.create(**fields(mine, workout=None))
    with pytest.raises(IntegrityError, match="planning_export_workout_owner"), transaction.atomic():
        WorkoutExport.objects.filter(pk=export.pk).update(workout=theirs)
    WorkoutExport.objects.filter(pk=export.pk).update(workout=mine)
    export.refresh_from_db()
    assert export.workout_id == mine.pk
