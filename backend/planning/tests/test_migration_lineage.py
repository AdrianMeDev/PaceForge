"""The migration that gives a workout a lineage: what exists keeps its key at Intervals.icu."""

from collections.abc import Iterator
from datetime import date, timedelta
from typing import Any

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

BEFORE = [("planning", "0003_workoutexport")]
MONDAY = date(2027, 7, 12)


@pytest.fixture
def before_the_migration(transactional_db: None) -> Iterator[Any]:
    """The schema and models as they were before the lineage."""
    executor = MigrationExecutor(connection)
    executor.migrate(BEFORE)
    yield executor.loader.project_state(BEFORE).apps
    migrate_forward()


def migrate_forward() -> None:
    executor = MigrationExecutor(connection)
    executor.migrate(executor.loader.graph.leaf_nodes())


def legacy_week(apps: Any, email: str, workouts: int, version: int = 1) -> list[Any]:
    """A user with a plan of ``workouts`` workouts, written with the models of the old schema."""
    user_model = apps.get_model("accounts", "User")
    plan_model = apps.get_model("planning", "WeeklyPlan")
    workout_model = apps.get_model("planning", "PlannedWorkout")
    user = user_model.objects.filter(email=email).first() or user_model.objects.create(
        email=email, password="x"
    )
    plan = plan_model.objects.create(owner=user, week_start=MONDAY, version=version)
    return [
        workout_model.objects.create(
            owner=user,
            plan=plan,
            day=MONDAY + timedelta(days=n),
            position=0,
            sport="running",
            title=f"Run {n}",
            goal="endurance",
            duration_minutes=60,
        )
        for n in range(workouts)
    ]


def lineages() -> dict[Any, Any]:
    with connection.cursor() as cursor:
        cursor.execute("SELECT id, lineage FROM planning_plannedworkout")
        return dict(cursor.fetchall())


class TestTheMigration:
    def test_every_existing_workout_is_its_own_lineage(self, before_the_migration: Any) -> None:
        rows = legacy_week(before_the_migration, "a@example.com", 3)
        rows += legacy_week(before_the_migration, "b@example.com", 2)

        migrate_forward()

        found = lineages()
        assert set(found) == {row.pk for row in rows}
        assert all(workout_id == lineage for workout_id, lineage in found.items())

    def test_the_key_of_an_event_that_is_in_a_calendar_stays_the_same(
        self, before_the_migration: Any
    ) -> None:
        rows = legacy_week(before_the_migration, "a@example.com", 2)
        keys_before = {f"paceforge-{row.pk}" for row in rows}

        migrate_forward()

        assert {f"paceforge-{lineage}" for lineage in lineages().values()} == keys_before

    def test_a_week_with_several_workouts_does_not_trip_the_constraint(
        self, before_the_migration: Any
    ) -> None:
        # One value for all of them would break the uniqueness of a lineage within a plan.
        legacy_week(before_the_migration, "a@example.com", 5)

        migrate_forward()

        assert len(set(lineages().values())) == 5

    def test_the_versions_of_a_week_before_it_are_different_lineages(
        self, before_the_migration: Any
    ) -> None:
        first = legacy_week(before_the_migration, "a@example.com", 1, version=1)
        second = legacy_week(before_the_migration, "a@example.com", 1, version=2)

        migrate_forward()

        assert lineages()[first[0].pk] != lineages()[second[0].pk]

    def test_it_works_on_an_empty_table(self, before_the_migration: Any) -> None:
        migrate_forward()

        assert lineages() == {}

    def test_it_can_be_reversed(self, before_the_migration: Any) -> None:
        rows = legacy_week(before_the_migration, "a@example.com", 2)
        migrate_forward()

        executor = MigrationExecutor(connection)
        executor.migrate(BEFORE)

        with connection.cursor() as cursor:
            cursor.execute("SELECT id FROM planning_plannedworkout")
            assert {pk for (pk,) in cursor.fetchall()} == {row.pk for row in rows}
