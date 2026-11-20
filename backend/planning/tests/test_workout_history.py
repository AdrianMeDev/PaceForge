"""Stored plan status protects history across ORM write paths and transactions."""

from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from typing import Any
from uuid import uuid7

import pytest
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from accounts.models import User
from planning.models import PlannedWorkout, WeeklyPlan, WorkoutExport

from .test_workout_scope import MONDAY, fields, wait_until_blocked

pytestmark = pytest.mark.django_db
FROZEN = ["confirmed", "superseded", "discarded"]


@pytest.fixture
def plans() -> tuple[WeeklyPlan, WeeklyPlan, PlannedWorkout]:
    owner = User.objects.create_user("history@example.com")
    source = WeeklyPlan.objects.create(owner=owner, week_start=MONDAY)
    target = WeeklyPlan.objects.create(owner=owner, week_start=MONDAY, version=2)
    return source, target, PlannedWorkout.objects.create(**fields(source))


def freeze(plan: WeeklyPlan, status: str = "confirmed") -> None:
    # Keep the caller's cached draft instance stale deliberately.
    WeeklyPlan.objects.filter(pk=plan.pk).update(
        status=status, confirmed_at=timezone.now() if status != "discarded" else None
    )


def check_deferred() -> None:
    with connection.cursor() as cursor:
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")


@pytest.mark.parametrize("status", FROZEN)
@pytest.mark.parametrize(
    "method",
    [
        "create",
        "save_new",
        "bulk_create",
        "save",
        "update",
        "move_save",
        "move_update",
        "delete",
        "queryset_delete",
    ],
)
def test_frozen_source_rejects_writes(
    plans: tuple[WeeklyPlan, WeeklyPlan, PlannedWorkout], status: str, method: str
) -> None:
    source, target, row = plans
    freeze(source, status)
    with pytest.raises(IntegrityError, match="planning_workout_history"), transaction.atomic():
        if method == "create":
            PlannedWorkout.objects.create(**fields(source, position=1))
        elif method == "save_new":
            PlannedWorkout(**fields(source, position=1)).save()
        elif method == "bulk_create":
            PlannedWorkout.objects.bulk_create(
                [
                    PlannedWorkout(**fields(target)),
                    PlannedWorkout(**fields(source, position=1)),
                ]
            )
        elif method == "save":
            row.title = "Changed"
            row.save()
        elif method == "update":
            source.workouts.update(title="Changed")
        elif method == "move_save":
            row.plan = target
            row.save()
        elif method == "move_update":
            source.workouts.update(plan=target)
        elif method == "delete":
            row.delete()
        else:
            source.workouts.all().delete()
        check_deferred()
    stored = PlannedWorkout.objects.get()
    assert (stored.plan_id, stored.title) == (source.pk, "Run")


@pytest.mark.parametrize("status", FROZEN)
@pytest.mark.parametrize("method", ["save", "update"])
def test_frozen_destination_rejects_moves(
    plans: tuple[WeeklyPlan, WeeklyPlan, PlannedWorkout], status: str, method: str
) -> None:
    source, target, row = plans
    freeze(target, status)
    with pytest.raises(IntegrityError, match="planning_workout_history"), transaction.atomic():
        if method == "save":
            row.plan = target
            row.save()
        else:
            source.workouts.update(plan=target)
    row.refresh_from_db()
    assert row.plan_id == source.pk


@pytest.mark.parametrize(
    "field,value",
    [
        ("owner_id", None),
        ("day", MONDAY),
        ("position", 1),
        ("sport", "cycling"),
        ("title", "Changed"),
        ("goal", "tempo"),
        ("duration_minutes", 30),
        ("segments", []),
        ("exercises", []),
        ("zone_system", ""),
        ("zone", None),
        ("notes", "Changed"),
        ("slot", "morning"),
        ("stretching_minutes", 5),
        ("lineage", None),
    ],
)
def test_every_workout_field_is_guarded(
    plans: tuple[WeeklyPlan, WeeklyPlan, PlannedWorkout], field: str, value: Any
) -> None:
    source, _, row = plans
    freeze(source)
    if field == "owner_id":
        value = source.owner_id
    elif field == "lineage":
        value = uuid7()
    with pytest.raises(IntegrityError, match="planning_workout_history"), transaction.atomic():
        PlannedWorkout.objects.filter(pk=row.pk).update(**{field: value})


@pytest.mark.parametrize("method", ["update", "bulk_update", "delete"])
def test_mixed_batch_rolls_back(
    plans: tuple[WeeklyPlan, WeeklyPlan, PlannedWorkout], method: str
) -> None:
    source, target, row = plans
    draft = PlannedWorkout.objects.create(**fields(target))
    freeze(source)
    with pytest.raises(IntegrityError, match="planning_workout_history"), transaction.atomic():
        if method == "update":
            PlannedWorkout.objects.update(title="Changed")
        elif method == "bulk_update":
            row.title = draft.title = "Changed"
            PlannedWorkout.objects.bulk_update([draft, row], ["title"])
        else:
            PlannedWorkout.objects.all().delete()
        check_deferred()
    assert PlannedWorkout.objects.count() == 2
    assert set(PlannedWorkout.objects.values_list("title", flat=True)) == {"Run"}


def test_draft_edits_moves_and_removal_before_confirmation_succeed(
    plans: tuple[WeeklyPlan, WeeklyPlan, PlannedWorkout],
) -> None:
    source, target, row = plans
    row.title = "Changed"
    row.save()
    source.workouts.update(plan=target)
    row.refresh_from_db()
    row.delete()
    freeze(target)
    check_deferred()
    assert not PlannedWorkout.objects.exists()


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("status", FROZEN)
@pytest.mark.parametrize("method", ["instance", "queryset"])
def test_whole_plan_deletion_keeps_detached_exports(
    plans: tuple[WeeklyPlan, WeeklyPlan, PlannedWorkout], status: str, method: str
) -> None:
    source, target, row = plans
    export = WorkoutExport.objects.create(
        owner=source.owner,
        week_start=MONDAY,
        workout=row,
        external_id="history",
        status="synced",
        event_id=1,
    )
    freeze(source, status)
    if method == "instance":
        source.delete()
    else:
        WeeklyPlan.objects.filter(pk=source.pk).delete()
    export.refresh_from_db()
    assert export.workout_id is None
    assert WeeklyPlan.objects.filter(pk=target.pk).exists()
    assert not PlannedWorkout.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_individual_delete_fails_at_commit_and_rolls_back(
    plans: tuple[WeeklyPlan, WeeklyPlan, PlannedWorkout],
) -> None:
    source, _, row = plans
    freeze(source)
    with pytest.raises(IntegrityError, match="planning_workout_history"):
        with transaction.atomic():
            source.workouts.all().delete()
            assert not PlannedWorkout.objects.filter(pk=row.pk).exists()
    assert PlannedWorkout.objects.filter(pk=row.pk).exists()


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("first", ["confirmation", "workout"])
@pytest.mark.parametrize("method", ["insert", "update", "move_in", "move_out", "delete"])
def test_confirmation_serializes_workout_changes(
    plans: tuple[WeeklyPlan, WeeklyPlan, PlannedWorkout], first: str, method: str
) -> None:
    source, target, row = plans
    incoming = PlannedWorkout.objects.create(**fields(target))
    pids: Queue[int] = Queue()

    def write(which: str) -> None:
        if which == "confirmation":
            freeze(source)
        elif method == "insert":
            PlannedWorkout.objects.create(**fields(source, position=1))
        elif method == "update":
            source.workouts.update(title="Changed")
        elif method == "move_in":
            PlannedWorkout.objects.filter(pk=incoming.pk).update(plan=source, position=1)
        elif method == "move_out":
            source.workouts.update(plan=target, position=1)
        else:
            source.workouts.all().delete()

    def concurrent_write() -> str:
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout = '15s'")
                cursor.execute("SELECT pg_backend_pid()")
                pids.put(cursor.fetchone()[0])
            with transaction.atomic():
                write("workout" if first == "confirmation" else "confirmation")
            return "accepted"
        except IntegrityError as error:
            assert "planning_workout_history" in str(error)
            return "rejected"
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=1) as pool:
        with transaction.atomic():
            write(first)
            future = pool.submit(concurrent_write)
            wait_until_blocked(pids.get(timeout=10))
        assert future.result(timeout=20) == ("rejected" if first == "confirmation" else "accepted")
    source.refresh_from_db()
    assert source.status == "confirmed"
    if first == "confirmation":
        row.refresh_from_db()
        assert (row.plan_id, row.title) == (source.pk, "Run")
    elif method == "insert":
        assert source.workouts.count() == 2
    elif method == "update":
        row.refresh_from_db()
        assert row.title == "Changed"
    elif method == "move_in":
        incoming.refresh_from_db()
        assert incoming.plan_id == source.pk
    elif method == "move_out":
        row.refresh_from_db()
        assert row.plan_id == target.pk
    else:
        assert not PlannedWorkout.objects.filter(pk=row.pk).exists()


def test_insert_cannot_precede_its_frozen_plan(
    plans: tuple[WeeklyPlan, WeeklyPlan, PlannedWorkout],
) -> None:
    source, _, _ = plans
    future_id = uuid7()
    with pytest.raises(IntegrityError, match="planning_workout_history"), transaction.atomic():
        PlannedWorkout.objects.bulk_create(
            [PlannedWorkout(**fields(source, plan_id=future_id, position=1))]
        )
        WeeklyPlan.objects.create(
            id=future_id,
            owner=source.owner,
            week_start=MONDAY,
            version=3,
            status="confirmed",
            confirmed_at=timezone.now(),
        )
        check_deferred()
    assert PlannedWorkout.objects.count() == 1
    assert not WeeklyPlan.objects.filter(pk=future_id).exists()
