"""Database guards keep reviews and both linked records with the same athlete."""

from collections.abc import Iterator
from typing import Any

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor

from accounts.models import User
from accounts.services.deletion import delete_account
from activities.models import Activity
from planning.models import PlannedWorkout
from reviews.models import WorkoutReview
from reviews.tests.builders import NOW, make_activity, make_plan

pytestmark = pytest.mark.django_db
GUARD = "reviews_review_link_owner"
BEFORE = [("reviews", "0003_weekfeedback_verdict")]
AFTER = [("reviews", "0004_review_link_owner")]


@pytest.fixture
def links() -> tuple[PlannedWorkout, PlannedWorkout, Activity, Activity]:
    owners = [User.objects.create_user(f"{name}@example.com") for name in ("alice", "bob")]
    workouts = [
        make_plan(owner, status="draft", workouts=2).workouts.order_by("day").first()
        for owner in owners
    ]
    assert workouts[0] is not None and workouts[1] is not None
    # Distinct starts let owner changes reach the review guard without a uniqueness conflict.
    activities = [
        make_activity(owner, f"2026-11-09T{hour:02d}:00:00")
        for owner, hour in zip(owners, (8, 9), strict=True)
    ]
    return workouts[0], workouts[1], activities[0], activities[1]


@pytest.mark.parametrize("field", ["workout", "activity"])
@pytest.mark.parametrize("method", ["create", "save", "bulk_create", "bulk_update", "update"])
@pytest.mark.parametrize("reverse", [False, True])
def test_cross_owner_links_are_refused_atomically(
    links: tuple[PlannedWorkout, PlannedWorkout, Activity, Activity],
    field: str,
    method: str,
    reverse: bool,
) -> None:
    mine, theirs, activity, other_activity = links
    if reverse:
        mine, theirs, activity, other_activity = theirs, mine, other_activity, activity
    target = theirs if field == "workout" else other_activity
    fields = {"owner_id": mine.owner_id, "workout": mine, "activity": activity}
    if method in ("create", "bulk_create"):
        with pytest.raises(IntegrityError, match=GUARD), transaction.atomic():
            if method == "create":
                WorkoutReview.objects.create(**{**fields, field: target})
            else:
                spare = mine.plan.workouts.exclude(pk=mine.pk).get()
                WorkoutReview.objects.bulk_create(
                    [
                        WorkoutReview(owner_id=mine.owner_id, workout=spare),
                        WorkoutReview(**{**fields, field: target}),
                    ]
                )
        assert not WorkoutReview.objects.exists()
    else:
        row = WorkoutReview.objects.create(**fields)
        with pytest.raises(IntegrityError, match=GUARD), transaction.atomic():
            if method == "update":
                WorkoutReview.objects.filter(pk=row.pk).update(**{field: target})
            else:
                setattr(row, field, target)
                if method == "save":
                    row.save()
                else:
                    WorkoutReview.objects.bulk_update([row], [field])
        row.refresh_from_db()
        assert (row.owner_id, row.workout_id, row.activity_id) == (
            mine.owner_id,
            mine.pk,
            activity.pk,
        )


@pytest.mark.parametrize("side", ["review", "workout", "activity"])
@pytest.mark.parametrize("method", ["save", "bulk_update", "update"])
def test_owner_changes_cannot_strand_reviews(
    links: tuple[PlannedWorkout, PlannedWorkout, Activity, Activity], side: str, method: str
) -> None:
    mine, theirs, activity, _ = links
    review = WorkoutReview.objects.create(owner_id=mine.owner_id, workout=mine, activity=activity)
    row = {"review": review, "workout": mine, "activity": activity}[side]
    fields: dict[str, Any] = {"owner_id": theirs.owner_id}
    # Keep the workout-plan owner check satisfied so it cannot mask this guard.
    if side == "workout":
        fields.update(plan=theirs.plan, position=1)
    original_owner = mine.owner_id
    with pytest.raises(IntegrityError, match=GUARD), transaction.atomic():
        if method == "update":
            type(row).objects.filter(pk=row.pk).update(**fields)
        else:
            for name, value in fields.items():
                setattr(row, name, value)
            if method == "save":
                row.save()
            else:
                type(row).objects.bulk_update(
                    [row], ["owner" if name == "owner_id" else name for name in fields]
                )
    row.refresh_from_db()
    assert row.owner_id == original_owner


def test_same_owner_links_null_activity_and_activity_deletion(
    links: tuple[PlannedWorkout, PlannedWorkout, Activity, Activity],
) -> None:
    mine, _, activity, _ = links
    review = WorkoutReview.objects.create(owner_id=mine.owner_id, workout=mine, status="done")
    replacement = mine.plan.workouts.exclude(pk=mine.pk).get()
    WorkoutReview.objects.filter(pk=review.pk).update(workout=replacement, activity=activity)
    activity.delete()
    review.refresh_from_db()
    assert (review.workout_id, review.activity_id, review.status) == (replacement.pk, None, "done")
    # Once detached, changing the activity's owner no longer strands a review.
    replacement_activity = make_activity(mine.owner, "2026-11-10T08:00:00")
    review.activity = replacement_activity
    review.save()
    review.activity = None
    review.save()
    replacement_activity.owner_id = links[1].owner_id
    replacement_activity.save()


def test_delete_account_with_reviews(
    links: tuple[PlannedWorkout, PlannedWorkout, Activity, Activity], transactional_db: None
) -> None:
    mine, theirs, activity, other_activity = links
    owner = mine.owner
    owner.set_password("review-test-password")
    owner.save()
    # Exercise deletion with a historical plan and its deferred workout removal guard too.
    plan = mine.plan
    plan.status = "confirmed"
    plan.confirmed_at = NOW
    plan.save()
    WorkoutReview.objects.create(owner=owner, workout=mine, activity=activity)
    surviving = WorkoutReview.objects.create(
        owner_id=theirs.owner_id, workout=theirs, activity=other_activity
    )
    owner_id = owner.pk
    delete_account(owner, password="review-test-password", confirmation=owner.email)
    assert not User.objects.filter(pk=owner_id).exists()
    assert not PlannedWorkout.objects.filter(owner_id=owner_id).exists()
    assert not Activity.objects.filter(owner_id=owner_id).exists()
    assert list(WorkoutReview.objects.values_list("pk", flat=True)) == [surviving.pk]


@pytest.fixture
def legacy_apps(transactional_db: None) -> Iterator[Any]:
    executor = MigrationExecutor(connection)
    leaves = executor.loader.graph.leaf_nodes()
    executor.migrate(BEFORE)
    apps = executor.loader.project_state(leaves).apps
    try:
        yield apps
    finally:
        apps.get_model("reviews", "WorkoutReview").objects.all().delete()
        MigrationExecutor(connection).migrate(leaves)


@pytest.mark.parametrize("field", ["workout", "activity"])
def test_preflight_refuses_invalid_existing_links(legacy_apps: Any, field: str) -> None:
    apps = legacy_apps
    users = apps.get_model("accounts", "User").objects
    owner = users.create(email="alice@example.com")
    other = users.create(email="bob@example.com")
    plan = apps.get_model("planning", "WeeklyPlan").objects.create(
        owner=other if field == "workout" else owner, week_start="2026-11-09"
    )
    workout = apps.get_model("planning", "PlannedWorkout").objects.create(
        owner_id=plan.owner_id,
        plan=plan,
        day="2026-11-09",
        sport="running",
        title="Run",
        goal="endurance",
        duration_minutes=60,
    )
    activity = apps.get_model("activities", "Activity").objects.create(
        owner=other if field == "activity" else owner,
        source="manual",
        sport="running",
        start_time="2026-11-09T08:00:00Z",
    )
    reviews = apps.get_model("reviews", "WorkoutReview").objects
    row = reviews.create(owner=owner, workout=workout, activity=activity)
    original = list(reviews.values())
    with pytest.raises(IntegrityError, match="invalid existing review links"):
        MigrationExecutor(connection).migrate(AFTER)
    assert list(reviews.values()) == original
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM pg_trigger WHERE tgname IN "
            "('reviews_review_link_owner', 'reviews_workout_review_owner', "
            "'reviews_activity_review_owner')"
        )
        assert cursor.fetchone()[0] == 0
    assert AFTER[0] not in MigrationExecutor(connection).loader.applied_migrations
    if field == "workout":
        row.owner = other
        activity.owner = other
        activity.save()
    else:
        row.activity = None
    row.save()
    MigrationExecutor(connection).migrate(AFTER)
    row.refresh_from_db()
    assert row.workout_id == workout.pk
    # Reversal removes all three guards and permits the old invalid pair again.
    MigrationExecutor(connection).migrate(BEFORE)
    reviews.filter(pk=row.pk).update(owner=owner if field == "workout" else other)
