"""Preflight refuses invalid legacy rows and restores the migration graph after tests."""

from collections.abc import Iterator
from datetime import date, timedelta
from typing import Any

import pytest
from django.db import IntegrityError, connection
from django.db.migrations.executor import MigrationExecutor

BEFORE = [("planning", "0006_weeklyplan_note")]
AFTER = [("planning", "0007_workout_plan_scope")]
MONDAY = date(2027, 7, 12)


@pytest.fixture
def legacy_apps(transactional_db: None) -> Iterator[Any]:
    executor = MigrationExecutor(connection)
    leaves = executor.loader.graph.leaf_nodes()
    executor.migrate(BEFORE)
    apps = executor.loader.project_state(BEFORE).apps
    try:
        yield apps
    finally:
        # Remove invalid fixtures before restoring every app's migrations.
        apps.get_model("planning", "PlannedWorkout").objects.all().delete()
        MigrationExecutor(connection).migrate(leaves)


def legacy_workout(apps: Any, kind: str) -> Any:
    users = apps.get_model("accounts", "User")
    owner = users.objects.create(email="alice@example.com", password="x")
    other = users.objects.create(email="bob@example.com", password="x")
    plan = apps.get_model("planning", "WeeklyPlan").objects.create(owner=owner, week_start=MONDAY)
    offset = {"before": -1, "after": 7, "monday": 0, "sunday": 6, "owner": 0}[kind]
    return apps.get_model("planning", "PlannedWorkout").objects.create(
        owner=other if kind == "owner" else owner,
        plan=plan,
        day=MONDAY + timedelta(days=offset),
        sport="running",
        title="Run",
        goal="endurance",
        duration_minutes=60,
    )


@pytest.mark.parametrize("kind", ["owner", "before", "after"])
def test_preflight_rejects_each_invalid_legacy_pair(legacy_apps: Any, kind: str) -> None:
    row = legacy_workout(legacy_apps, kind)
    with pytest.raises(IntegrityError, match="invalid existing workout-plan pairs"):
        MigrationExecutor(connection).migrate(AFTER)
    assert type(row).objects.filter(pk=row.pk).exists()
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM pg_trigger WHERE tgname IN "
            "('planning_workout_plan_scope', 'planning_plan_workout_scope')"
        )
        assert cursor.fetchone()[0] == 0
    assert ("planning", "0007_workout_plan_scope") not in MigrationExecutor(
        connection
    ).loader.applied_migrations
    row.owner_id = row.plan.owner_id
    row.day = MONDAY
    row.save()
    MigrationExecutor(connection).migrate(AFTER)


@pytest.mark.parametrize("kind", ["monday", "sunday"])
def test_valid_boundaries_survive_and_reversal_removes_enforcement(
    legacy_apps: Any, kind: str
) -> None:
    row = legacy_workout(legacy_apps, kind)
    MigrationExecutor(connection).migrate(AFTER)
    row.refresh_from_db()
    assert row.day == MONDAY + timedelta(days=0 if kind == "monday" else 6)
    with pytest.raises(IntegrityError, match="planning_workout_plan_scope"):
        type(row).objects.filter(pk=row.pk).update(day=MONDAY + timedelta(days=7))
    MigrationExecutor(connection).migrate(BEFORE)
    type(row).objects.filter(pk=row.pk).update(day=MONDAY + timedelta(days=7))


def test_empty_database_migrates(legacy_apps: Any) -> None:
    MigrationExecutor(connection).migrate(AFTER)


EXPORT_AFTER = [("planning", "0008_export_workout_owner")]


@pytest.fixture
def legacy_export_apps(transactional_db: None) -> Iterator[Any]:
    executor = MigrationExecutor(connection)
    leaves = executor.loader.graph.leaf_nodes()
    executor.migrate(AFTER)
    apps = executor.loader.project_state(AFTER).apps
    try:
        yield apps
    finally:
        apps.get_model("planning", "WorkoutExport").objects.all().delete()
        MigrationExecutor(connection).migrate(leaves)


@pytest.mark.parametrize("other_owner", [False, True])
def test_export_preflight_refuses_legacy_mismatch_without_losing_detached_event(
    legacy_export_apps: Any, other_owner: bool
) -> None:
    apps = legacy_export_apps
    workout = legacy_workout(apps, "monday")
    original_owner_id = workout.owner_id
    other = apps.get_model("accounts", "User").objects.get(email="bob@example.com")
    exports = apps.get_model("planning", "WorkoutExport").objects
    if other_owner:
        plan = apps.get_model("planning", "WeeklyPlan").objects.create(
            owner=other, week_start=MONDAY
        )
        type(workout).objects.filter(pk=workout.pk).update(owner=other, plan=plan)
        workout.refresh_from_db()
    invalid = exports.create(
        owner_id=original_owner_id if other_owner else other.pk,
        workout=workout,
        week_start=MONDAY,
        external_id="linked",
        event_id=123,
        status="synced",
    )
    detached = exports.create(
        owner_id=workout.owner_id,
        workout=None,
        week_start=MONDAY,
        external_id="detached",
        event_id=456,
        status="synced",
    )
    with pytest.raises(IntegrityError, match="invalid existing export-workout pairs"):
        MigrationExecutor(connection).migrate(EXPORT_AFTER)
    invalid.refresh_from_db()
    assert invalid.owner_id != workout.owner_id
    assert invalid.event_id == 123
    detached.refresh_from_db()
    assert detached.workout_id is None
    assert detached.event_id == 456
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM pg_trigger WHERE tgname IN "
            "('planning_export_workout_owner', 'planning_workout_export_owner')"
        )
        assert cursor.fetchone()[0] == 0
    assert ("planning", "0008_export_workout_owner") not in MigrationExecutor(
        connection
    ).loader.applied_migrations
    invalid.owner_id = workout.owner_id
    invalid.save()
    MigrationExecutor(connection).migrate(EXPORT_AFTER)
    invalid.refresh_from_db()
    detached.refresh_from_db()
    assert (invalid.workout_id, invalid.event_id) == (workout.pk, 123)
    assert (detached.workout_id, detached.event_id) == (None, 456)


def test_export_migration_reversal_removes_both_guards(legacy_export_apps: Any) -> None:
    apps = legacy_export_apps
    workout = legacy_workout(apps, "monday")
    other = apps.get_model("accounts", "User").objects.get(email="bob@example.com")
    exports = apps.get_model("planning", "WorkoutExport").objects
    row = exports.create(
        owner_id=workout.owner_id,
        workout=workout,
        week_start=MONDAY,
        external_id="linked",
        event_id=123,
        status="synced",
    )
    MigrationExecutor(connection).migrate(EXPORT_AFTER)
    with pytest.raises(IntegrityError, match="planning_export_workout_owner"):
        exports.filter(pk=row.pk).update(owner=other)
    MigrationExecutor(connection).migrate(AFTER)
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM pg_trigger WHERE tgname IN "
            "('planning_export_workout_owner', 'planning_workout_export_owner')"
        )
        assert cursor.fetchone()[0] == 0
    exports.filter(pk=row.pk).update(owner=other)


def test_empty_database_accepts_export_migration(legacy_export_apps: Any) -> None:
    MigrationExecutor(connection).migrate(EXPORT_AFTER)


REVISION_AFTER = [("planning", "0009_revision_ancestry")]


@pytest.fixture
def legacy_revision_apps(transactional_db: None) -> Iterator[Any]:
    executor = MigrationExecutor(connection)
    leaves = executor.loader.graph.leaf_nodes()
    executor.migrate(EXPORT_AFTER)
    apps = executor.loader.project_state(EXPORT_AFTER).apps
    try:
        yield apps
    finally:
        apps.get_model("planning", "WeeklyPlan").objects.all().delete()
        MigrationExecutor(connection).migrate(leaves)


@pytest.mark.parametrize("kind", ["owner", "week", "order", "cycle2", "cycle3"])
def test_revision_preflight_refuses_invalid_legacy_edges_atomically(
    legacy_revision_apps: Any, kind: str
) -> None:
    apps = legacy_revision_apps
    owner = apps.get_model("accounts", "User").objects.create(email="alice@example.com")
    other = apps.get_model("accounts", "User").objects.create(email="bob@example.com")
    plans = apps.get_model("planning", "WeeklyPlan").objects
    root = plans.create(owner=owner, week_start=MONDAY, version=3)
    child = plans.create(
        owner=other if kind == "owner" else owner,
        week_start=MONDAY + timedelta(weeks=1) if kind == "week" else MONDAY,
        version=1 if kind == "order" else 5,
        parent=root,
    )
    if kind.startswith("cycle"):
        last = child
        if kind == "cycle3":
            last = plans.create(owner=owner, week_start=MONDAY, version=7, parent=child)
        plans.filter(pk=root.pk).update(parent=last)
    original = list(plans.order_by("id").values())
    with pytest.raises(IntegrityError, match="invalid existing parent edges"):
        MigrationExecutor(connection).migrate(REVISION_AFTER)
    assert list(plans.order_by("id").values()) == original
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM pg_trigger WHERE tgname = 'planning_revision_ancestry'"
        )
        assert cursor.fetchone()[0] == 0
        cursor.execute(
            "SELECT count(*) FROM pg_proc WHERE proname = 'planning_check_revision_ancestry'"
        )
        assert cursor.fetchone()[0] == 0
    assert ("planning", "0009_revision_ancestry") not in MigrationExecutor(
        connection
    ).loader.applied_migrations
    # Correct the fixtures explicitly; the migration must never silently repair them.
    plans.filter(pk=root.pk).update(parent=None)
    plans.filter(pk=child.pk).update(owner=owner, week_start=MONDAY, version=5)
    MigrationExecutor(connection).migrate(REVISION_AFTER)


def test_revision_preflight_preserves_branched_history_and_reverses(
    legacy_revision_apps: Any,
) -> None:
    apps = legacy_revision_apps
    owner = apps.get_model("accounts", "User").objects.create(email="alice@example.com")
    plans = apps.get_model("planning", "WeeklyPlan").objects
    root = plans.create(owner=owner, week_start=MONDAY, version=1)
    first = plans.create(owner=owner, week_start=MONDAY, version=4, parent=root)
    second = plans.create(owner=owner, week_start=MONDAY, version=8, parent=root)
    plans.create(owner=owner, week_start=MONDAY, version=12, parent=first)
    original = list(plans.order_by("id").values())
    MigrationExecutor(connection).migrate(REVISION_AFTER)
    assert list(plans.order_by("id").values()) == original
    with pytest.raises(IntegrityError, match="planning_revision_ancestry"):
        plans.filter(pk=root.pk).update(parent=second)
    MigrationExecutor(connection).migrate(EXPORT_AFTER)
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM pg_trigger WHERE tgname = 'planning_revision_ancestry'"
        )
        assert cursor.fetchone()[0] == 0
        cursor.execute(
            "SELECT count(*) FROM pg_proc WHERE proname = 'planning_check_revision_ancestry'"
        )
        assert cursor.fetchone()[0] == 0
    plans.filter(pk=root.pk).update(parent=second)


def test_empty_database_accepts_revision_migration(legacy_revision_apps: Any) -> None:
    MigrationExecutor(connection).migrate(REVISION_AFTER)
