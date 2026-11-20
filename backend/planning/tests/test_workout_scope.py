"""Workout scope is enforced even without model validation."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from queue import Queue
from time import monotonic, sleep
from typing import Any

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.models import F

from accounts.models import User
from planning.models import PlannedWorkout, WeeklyPlan

MONDAY = date(2027, 7, 12)
pytestmark = pytest.mark.django_db


@pytest.fixture
def pair() -> tuple[WeeklyPlan, User]:
    owner = User.objects.create_user("alice@example.com")
    other = User.objects.create_user("bob@example.com")
    return WeeklyPlan.objects.create(owner=owner, week_start=MONDAY), other


def fields(plan: WeeklyPlan, **changes: Any) -> dict[str, Any]:
    return {
        "owner_id": plan.owner_id,
        "plan": plan,
        "day": MONDAY,
        "sport": "running",
        "title": "Run",
        "goal": "endurance",
        "duration_minutes": 60,
        **changes,
    }


@pytest.mark.parametrize("kind", ["owner", "before", "after"])
@pytest.mark.parametrize("method", ["create", "save", "bulk_create", "update", "reparent"])
def test_invalid_workout_writes_are_atomic(
    pair: tuple[WeeklyPlan, User], kind: str, method: str
) -> None:
    plan, other = pair
    changes = (
        {"owner_id": other.pk}
        if kind == "owner"
        else {"day": MONDAY + timedelta(days=-1 if kind == "before" else 7)}
    )
    existing = PlannedWorkout.objects.create(**fields(plan))
    target = WeeklyPlan.objects.create(
        owner=other if kind == "owner" else plan.owner,
        week_start=MONDAY if kind == "owner" else MONDAY + timedelta(weeks=1),
        version=2,
    )
    with pytest.raises(IntegrityError, match="planning_workout_plan_scope"), transaction.atomic():
        if method == "create":
            PlannedWorkout.objects.create(**fields(plan, position=1, **changes))
        elif method == "save":
            for field, value in changes.items():
                setattr(existing, field, value)
            existing.save()
        elif method == "bulk_create":
            PlannedWorkout.objects.bulk_create(
                [
                    PlannedWorkout(**fields(plan, position=2)),
                    PlannedWorkout(**fields(plan, position=1, **changes)),
                ]
            )
        elif method == "update":
            PlannedWorkout.objects.filter(pk=existing.pk).update(**changes)
        else:
            PlannedWorkout.objects.filter(pk=existing.pk).update(plan=target)
    existing.refresh_from_db()
    assert PlannedWorkout.objects.count() == 1
    assert (existing.owner_id, existing.day, existing.plan_id) == (plan.owner_id, MONDAY, plan.pk)


@pytest.mark.parametrize("offset", range(7))
def test_each_day_including_both_boundaries_is_allowed(
    pair: tuple[WeeklyPlan, User], offset: int
) -> None:
    plan, _ = pair
    row = PlannedWorkout.objects.create(**fields(plan, day=MONDAY + timedelta(days=offset)))
    row.refresh_from_db()
    assert row.day == MONDAY + timedelta(days=offset)


def test_mixed_validity_queryset_update_rolls_back_every_row(
    pair: tuple[WeeklyPlan, User],
) -> None:
    plan, _ = pair
    first = PlannedWorkout.objects.create(**fields(plan))
    last = PlannedWorkout.objects.create(**fields(plan, day=MONDAY + timedelta(days=6)))
    with pytest.raises(IntegrityError, match="planning_workout_plan_scope"), transaction.atomic():
        plan.workouts.update(day=F("day") + timedelta(days=1))
    first.refresh_from_db()
    last.refresh_from_db()
    assert (first.day, last.day) == (MONDAY, MONDAY + timedelta(days=6))


@pytest.mark.parametrize("field", ["owner_id", "week_start"])
@pytest.mark.parametrize("method", ["save", "update"])
def test_plan_changes_cannot_strand_workouts(
    pair: tuple[WeeklyPlan, User], field: str, method: str
) -> None:
    plan, other = pair
    PlannedWorkout.objects.create(**fields(plan))
    value = other.pk if field == "owner_id" else MONDAY + timedelta(weeks=1)
    with pytest.raises(IntegrityError, match="planning_workout_plan_scope"), transaction.atomic():
        if method == "save":
            setattr(plan, field, value)
            plan.save()
        else:
            WeeklyPlan.objects.filter(pk=plan.pk).update(**{field: value})
    plan.refresh_from_db()
    assert plan.owner_id != other.pk
    assert plan.week_start == MONDAY


def test_empty_plan_changes_and_valid_reparenting_are_allowed(
    pair: tuple[WeeklyPlan, User],
) -> None:
    plan, other = pair
    target = WeeklyPlan.objects.create(owner=other, week_start=MONDAY, version=2)
    target.owner_id = plan.owner_id
    target.week_start = MONDAY + timedelta(weeks=1)
    target.save()
    target.week_start = MONDAY
    target.save()
    row = PlannedWorkout.objects.create(**fields(plan))
    row.plan = target
    row.save()
    row.refresh_from_db()
    assert row.plan_id == target.pk


def wait_until_blocked(pid: int) -> None:
    deadline = monotonic() + 10
    while monotonic() < deadline:
        with connection.cursor() as cursor:
            cursor.execute("SELECT cardinality(pg_blocking_pids(%s))", [pid])
            if cursor.fetchone()[0]:
                return
        sleep(0.01)
    pytest.fail("The concurrent write did not wait for the plan row lock")


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("field", ["owner_id", "week_start"])
@pytest.mark.parametrize("first", ["plan", "workout"])
@pytest.mark.parametrize("method", ["insert", "reparent"])
def test_concurrent_plan_and_workout_changes_preserve_scope(
    pair: tuple[WeeklyPlan, User], field: str, first: str, method: str
) -> None:
    plan, other = pair
    source = WeeklyPlan.objects.create(owner=plan.owner, week_start=MONDAY, version=2)
    row = PlannedWorkout(**fields(source))
    if method == "reparent":
        row.save()
    changes = {field: other.pk if field == "owner_id" else MONDAY + timedelta(weeks=1)}
    pids: Queue[int] = Queue()

    def write(which: str) -> None:
        if which == "plan":
            WeeklyPlan.objects.filter(pk=plan.pk).update(**changes)
        elif method == "insert":
            PlannedWorkout.objects.create(**fields(plan))
        else:
            PlannedWorkout.objects.filter(pk=row.pk).update(plan=plan)

    def concurrent_write() -> str:
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout = '15s'")
                cursor.execute("SELECT pg_backend_pid()")
                pids.put(cursor.fetchone()[0])
            with transaction.atomic():
                write("workout" if first == "plan" else "plan")
            return "accepted"
        except IntegrityError as error:
            assert "planning_workout_plan_scope" in str(error)
            return "rejected"
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=1) as pool:
        with transaction.atomic():
            write(first)
            future = pool.submit(concurrent_write)
            wait_until_blocked(pids.get(timeout=10))
        assert future.result(timeout=20) == "rejected"
    plan.refresh_from_db()
    if first == "plan":
        assert not plan.workouts.exists()
        assert getattr(plan, field) == changes[field]
    else:
        stored = plan.workouts.get()
        assert stored.owner_id == plan.owner_id
        assert plan.week_start <= stored.day <= plan.week_start + timedelta(days=6)
