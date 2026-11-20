from datetime import UTC, datetime, timedelta

import pytest

from accounts.models import User
from goals import services as goal_services
from planning import services
from planning.models import PlannedWorkout, WeeklyPlan
from planning.schema import WeekPlan
from planning.tests.test_services import MONDAY, good_week, prepared, workout
from reviews.models import WorkoutReview
from reviews.services import carry_over, week_review

from .builders import make_activity

pytestmark = pytest.mark.django_db


@pytest.fixture
def alice() -> User:
    return prepared(User.objects.create_user("alice@example.com"))


@pytest.fixture
def bob() -> User:
    return prepared(User.objects.create_user("bob@example.com"))


def confirmed(user: User, week: WeekPlan | None = None) -> WeeklyPlan:
    plan = services.save_draft(user, week or good_week())
    return services.confirm(user, plan.pk)


def workouts_of(plan: WeeklyPlan) -> list[PlannedWorkout]:
    return list(PlannedWorkout.objects.filter(plan=plan).order_by("day", "position", "id"))


def next_version(user: User, old: WeeklyPlan, keep: int | None = None) -> WeeklyPlan:
    """A new draft made from ``old`` (its workouts and lineages; the first ``keep`` of them)."""
    copy = services.load(user, old.pk)
    workouts = copy.workouts if keep is None else copy.workouts[:keep]
    return services.save_draft(
        user, WeekPlan(copy.week_start, workouts, copy.rationale), parent=old.pk
    )


class TestConfirmingANewVersion:
    def test_what_the_user_said_about_a_workout_is_still_said_about_it(self, alice: User) -> None:
        old = confirmed(alice)
        first, second, third, fourth = workouts_of(old)
        run = make_activity(alice, "2026-11-09T07:00")
        WorkoutReview.objects.create(owner=alice, workout=first, activity=run, status="partial")
        WorkoutReview.objects.create(owner=alice, workout=second, no_activity=True)
        WorkoutReview.objects.create(owner=alice, workout=third, status="missed")

        newer = services.confirm(alice, next_version(alice, old).pk)

        moved = {w.lineage: w for w in workouts_of(newer)}
        assert WorkoutReview.objects.count() == 3
        row = WorkoutReview.objects.get(workout=moved[first.lineage])
        assert (row.activity, row.status, row.no_activity) == (run, "partial", False)
        assert WorkoutReview.objects.get(workout=moved[second.lineage]).no_activity is True
        assert WorkoutReview.objects.get(workout=moved[third.lineage]).status == "missed"
        assert not WorkoutReview.objects.filter(workout=moved[fourth.lineage]).exists()
        assert not WorkoutReview.objects.filter(workout__plan=old).exists()

    def test_the_decision_follows_a_workout_that_was_moved(self, alice: User) -> None:
        old = confirmed(alice, WeekPlan(MONDAY, (workout(MONDAY, 0, 30), workout(MONDAY, 2, 30))))
        first = workouts_of(old)[0]
        WorkoutReview.objects.create(owner=alice, workout=first, status="missed")
        copy = services.load(alice, old.pk)
        moved = WeekPlan(
            MONDAY,
            (
                workout(MONDAY, 4, 30, lineage=copy.workouts[0].lineage),
                copy.workouts[1],
            ),
        )
        newer = services.save_draft(alice, moved, parent=old.pk)

        newer = services.confirm(alice, newer.pk)

        row = WorkoutReview.objects.get()
        assert row.workout.plan_id == newer.pk
        assert row.workout.day == MONDAY + timedelta(days=4)
        assert row.workout.lineage == first.lineage

    def test_a_workout_that_is_gone_keeps_its_decision_with_the_old_version(
        self, alice: User
    ) -> None:
        old = confirmed(alice)
        gone = workouts_of(old)[3]
        WorkoutReview.objects.create(owner=alice, workout=gone, status="missed")

        newer = services.confirm(alice, next_version(alice, old, keep=3).pk)

        row = WorkoutReview.objects.get()
        assert row.workout == gone
        assert row.workout.plan_id == old.pk
        assert not WorkoutReview.objects.filter(workout__plan=newer).exists()

    def test_the_week_review_shows_the_moved_decision_and_not_the_gone_one(
        self, alice: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            goal_services, "_utc_now", lambda: datetime(2027, 7, 17, 12, tzinfo=UTC)
        )
        old = confirmed(alice)
        first, _, _, last = workouts_of(old)
        WorkoutReview.objects.create(owner=alice, workout=first, status="missed")
        WorkoutReview.objects.create(owner=alice, workout=last, status="missed")

        newer = services.confirm(alice, next_version(alice, old, keep=3).pk)

        review = week_review(alice, MONDAY)
        assert review.plan == newer
        shown = {found.workout_id: found for found in review.match.workouts}
        kept = next(w for w in review.workouts if w.lineage == first.lineage)
        assert (shown[kept.pk].status.value, shown[kept.pk].status_origin.value) == (
            "missed",
            "user",
        )
        assert len(review.match.workouts) == 3

    def test_a_first_version_has_nothing_to_carry(self, alice: User) -> None:
        plan = confirmed(alice)

        assert plan.status == WeeklyPlan.Status.CONFIRMED
        assert not WorkoutReview.objects.exists()

    def test_a_draft_the_coach_made_anew_gets_none_of_it(self, alice: User) -> None:
        old = confirmed(alice)
        WorkoutReview.objects.create(owner=alice, workout=workouts_of(old)[0], status="missed")
        fresh = services.save_draft(alice, good_week(rationale="Again"), parent=old.pk)

        newer = services.confirm(alice, fresh.pk)

        row = WorkoutReview.objects.get()
        assert row.workout.plan_id == old.pk  # all lineages are new: nothing was the same training
        assert not WorkoutReview.objects.filter(workout__plan=newer).exists()

    def test_it_happens_in_the_transaction_of_the_confirmation(
        self, alice: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        old = confirmed(alice)
        WorkoutReview.objects.create(owner=alice, workout=workouts_of(old)[0], status="missed")
        draft = next_version(alice, old)

        def fail(*args: object) -> int:
            raise RuntimeError("boom")

        monkeypatch.setattr(services, "carry_over", fail)
        with pytest.raises(RuntimeError):
            services.confirm(alice, draft.pk)

        old.refresh_from_db()
        draft.refresh_from_db()
        assert (old.status, draft.status) == ("confirmed", "draft")  # nothing was half done
        assert WorkoutReview.objects.get().workout.plan_id == old.pk


class TestCarryingOver:
    def test_it_says_how_many_decisions_moved(self, alice: User) -> None:
        old = confirmed(alice)
        for row in workouts_of(old)[:2]:
            WorkoutReview.objects.create(owner=alice, workout=row, status="missed")
        newer = next_version(alice, old)

        assert carry_over(alice, old, newer) == 2
        assert carry_over(alice, old, newer) == 0  # nothing is left with the old version

    def test_a_plan_without_decisions_changes_nothing(self, alice: User) -> None:
        old = confirmed(alice)

        assert carry_over(alice, old, next_version(alice, old)) == 0

    def test_a_version_that_shares_no_lineage_takes_nothing(self, alice: User) -> None:
        old = confirmed(alice)
        WorkoutReview.objects.create(owner=alice, workout=workouts_of(old)[0], status="done")
        other = services.save_draft(alice, good_week(rationale="Again"), parent=old.pk)

        assert carry_over(alice, old, other) == 0

    def test_the_decisions_of_another_user_are_never_moved(self, alice: User, bob: User) -> None:
        mine = confirmed(alice)
        theirs = services.save_draft(bob, good_week())
        # Set up matching lineages while Bob's plan is still a draft.
        for mine_row, their_row in zip(workouts_of(mine), workouts_of(theirs), strict=True):
            PlannedWorkout.objects.filter(pk=their_row.pk).update(lineage=mine_row.lineage)
        theirs = services.confirm(bob, theirs.pk)
        for plan, user in ((mine, alice), (theirs, bob)):
            WorkoutReview.objects.create(owner=user, workout=workouts_of(plan)[0], status="missed")
        newer = next_version(bob, theirs)

        assert carry_over(alice, mine, newer) == 0
        assert carry_over(bob, mine, newer) == 0
        assert WorkoutReview.objects.get(owner=alice).workout.plan_id == mine.pk

    def test_other_weeks_are_left_alone(self, alice: User) -> None:
        week = confirmed(alice)
        later = MONDAY + timedelta(days=7)
        other = confirmed(alice, WeekPlan(later, (workout(later, 0, 30),)))
        WorkoutReview.objects.create(owner=alice, workout=workouts_of(other)[0], status="done")

        carry_over(alice, week, next_version(alice, week))

        assert WorkoutReview.objects.get().workout.plan_id == other.pk
