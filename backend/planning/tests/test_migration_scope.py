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
