from datetime import UTC, date, datetime, timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from accounts.models import User
from athletes.models import AthleteProfile
from goals import services as goal_services
from planning.models import PlannedWorkout
from reviews.matching import Origin, Status
from reviews.models import WeekComment, WeekFeedback, WorkoutReview
from reviews.services import (
    REVIEW_WEEKS,
    WeekNotReviewable,
    has_anything,
    reviewable_weeks,
    week_review,
    week_summary,
)

from .builders import MONDAY, NOW, make_activity, make_plan

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(goal_services, "_utc_now", lambda: NOW)


@pytest.fixture
def alice() -> User:
    return User.objects.create_user("alice@example.com")


@pytest.fixture
def bob() -> User:
    return User.objects.create_user("bob@example.com")


class TestWeeks:
    def test_the_current_week_and_four_before_it_oldest_first(self, alice: User) -> None:
        assert REVIEW_WEEKS == 4
        assert reviewable_weeks(alice) == tuple(
            MONDAY - timedelta(weeks=n) for n in (4, 3, 2, 1, 0)
        )

    def test_what_week_it_is_depends_on_the_time_zone(
        self, alice: User, bob: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 23:30 UTC on a Sunday: already Monday in Berlin, still Sunday afternoon in Los Angeles.
        sunday_night = datetime(2026, 11, 15, 23, 30, tzinfo=UTC)
        monkeypatch.setattr(goal_services, "_utc_now", lambda: sunday_night)
        AthleteProfile.objects.create(owner=alice, timezone="Europe/Berlin")
        AthleteProfile.objects.create(owner=bob, timezone="America/Los_Angeles")

        assert reviewable_weeks(alice)[-1] == MONDAY + timedelta(days=7)
        assert reviewable_weeks(bob)[-1] == MONDAY

    @pytest.mark.parametrize("offset", [-6, 1, 3])
    def test_a_week_outside_the_range_is_refused(self, alice: User, offset: int) -> None:
        with pytest.raises(WeekNotReviewable):
            week_review(alice, MONDAY + timedelta(weeks=offset))

    def test_a_day_that_is_no_monday_is_refused(self, alice: User) -> None:
        with pytest.raises(WeekNotReviewable):
            week_review(alice, MONDAY + timedelta(days=1))

    def test_the_oldest_week_and_the_current_one_can_be_reviewed(self, alice: User) -> None:
        for monday in (MONDAY - timedelta(weeks=REVIEW_WEEKS), MONDAY):
            assert week_review(alice, monday).week_start == monday


class TestAWeek:
    def test_a_week_without_anything(self, alice: User) -> None:
        review = week_review(alice, MONDAY)

        assert review.plan is None
        assert review.workouts == () and review.activities == ()
        assert review.match.workouts == () and review.match.unplanned == ()
        assert review.comparison.sports == ()
        assert review.feedback is None
        assert review.today == date(2026, 11, 14)

    def test_the_confirmed_plan_with_its_activities_and_feedback(self, alice: User) -> None:
        plan = make_plan(alice, workouts=2)
        run = make_activity(alice, "2026-11-09T07:00", rpe=6, notes="felt good")
        extra = make_activity(alice, "2026-11-12T18:00", sport="strength", timer_seconds=1800.0)
        feedback = WeekFeedback.objects.create(owner=alice, week_start=MONDAY, fatigue=3)

        review = week_review(alice, MONDAY)

        assert review.plan == plan
        assert [workout.title for workout in review.workouts] == ["Run 0", "Run 1"]
        assert [activity.pk for activity in review.activities] == [run.pk, extra.pk]
        first, second = review.match.workouts
        assert (first.status, first.activity_id, first.activity_origin) == (
            Status.DONE,
            run.pk,
            Origin.AUTO,
        )
        assert (second.status, second.activity_id) == (Status.MISSED, None)
        assert review.match.unplanned == (extra.pk,)
        assert review.feedback == feedback
        running = next(e.figures for e in review.comparison.sports if e.sport == "running")
        assert (running.planned_minutes, running.actual_minutes, running.load) == (120, 60, 60)

    def test_the_corrections_of_the_user_are_applied(self, alice: User) -> None:
        make_plan(alice, workouts=2)
        run = make_activity(alice, "2026-11-09T07:00")
        later = make_activity(alice, "2026-11-10T07:00")
        first, second = week_review(alice, MONDAY).workouts
        WorkoutReview.objects.create(owner=alice, workout=first, status="missed")
        WorkoutReview.objects.create(owner=alice, workout=second, activity=run)

        review = week_review(alice, MONDAY)

        by_workout = {found.workout_id: found for found in review.match.workouts}
        assert by_workout[first.pk].status is Status.MISSED
        assert by_workout[first.pk].status_origin is Origin.USER
        assert by_workout[second.pk].activity_id == run.pk
        assert by_workout[second.pk].activity_origin is Origin.USER
        assert review.match.unplanned == (later.pk,)

    def test_only_the_confirmed_version_is_reviewed(self, alice: User) -> None:
        make_plan(alice, status="superseded", workouts=3)
        make_plan(alice, status="draft", workouts=4)
        confirmed = make_plan(alice, status="confirmed", workouts=1)
        make_plan(alice, status="discarded", workouts=5)

        review = week_review(alice, MONDAY)

        assert review.plan == confirmed
        assert len(review.workouts) == 1

    def test_a_draft_is_not_a_plan_to_review(self, alice: User) -> None:
        make_plan(alice, status="draft", workouts=2)

        assert week_review(alice, MONDAY).plan is None

    def test_the_week_is_the_local_week_a_session_just_after_midnight_belongs_to_that_day(
        self, alice: User
    ) -> None:
        AthleteProfile.objects.create(owner=alice, timezone="Europe/Berlin")
        # 23:30 UTC on Sunday the 8th is 00:30 on Monday the 9th in Berlin: this week.
        early = make_activity(alice, "2026-11-08T23:30")
        # 22:30 UTC on Sunday the 15th is 23:30 that Sunday in Berlin: still this week.
        late = make_activity(alice, "2026-11-15T22:30")
        # 23:30 UTC on Sunday the 15th is 00:30 on Monday the 16th in Berlin: the next one.
        next_week = make_activity(alice, "2026-11-15T23:30")
        # 22:30 UTC on Saturday the 7th is 23:30 on that Saturday in Berlin: the one before.
        before = make_activity(alice, "2026-11-07T22:30")

        review = week_review(alice, MONDAY)

        assert [activity.pk for activity in review.activities] == [early.pk, late.pk]
        assert review.activity_days[early.pk] == MONDAY
        assert review.activity_days[late.pk] == MONDAY + timedelta(days=6)
        assert {next_week.pk, before.pk}.isdisjoint(review.activity_days)

    def test_without_a_time_zone_the_week_is_that_of_utc(self, alice: User) -> None:
        inside = make_activity(alice, "2026-11-09T00:00")
        make_activity(alice, "2026-11-08T23:59")
        make_activity(alice, "2026-11-16T00:00")

        assert [activity.pk for activity in week_review(alice, MONDAY).activities] == [inside.pk]

    def test_a_workout_is_matched_on_the_local_day_of_the_session(self, alice: User) -> None:
        AthleteProfile.objects.create(owner=alice, timezone="Europe/Berlin")
        make_plan(alice, workouts=1)  # Monday the 9th
        night = make_activity(alice, "2026-11-08T23:30")  # Monday 00:30 in Berlin

        found = week_review(alice, MONDAY).match.workouts[0]

        assert found.activity_id == night.pk

    def test_the_load_and_the_rating_come_from_the_activity(self, alice: User) -> None:
        make_plan(alice, workouts=1)
        make_activity(alice, "2026-11-09T07:00", rpe=5, timer_seconds=2700.0)
        make_activity(alice, "2026-11-10T07:00")

        total = week_review(alice, MONDAY).comparison.total

        assert (total.load, total.rated_count, total.actual_count) == (38, 1, 2)

    def test_other_users_data_never_appears(self, alice: User, bob: User) -> None:
        plan = make_plan(bob, workouts=3)
        make_activity(bob, "2026-11-09T07:00")
        WeekFeedback.objects.create(owner=bob, week_start=MONDAY, pain=5)
        WorkoutReview.objects.create(owner=bob, workout=plan.workouts.all()[0], status="done")

        review = week_review(alice, MONDAY)

        assert review.plan is None and review.workouts == () and review.activities == ()
        assert review.feedback is None
        mine = week_review(bob, MONDAY)
        assert len(mine.workouts) == 3 and mine.feedback is not None

    def test_it_takes_the_same_number_of_queries_however_much_data_there_is(
        self, alice: User, bob: User
    ) -> None:
        make_plan(alice, workouts=1)
        make_activity(alice, "2026-11-09T07:00")
        with CaptureQueriesContext(connection) as small:
            week_review(alice, MONDAY)

        # Fourteen workouts in all (two a day) and 13 activities, five of them rated.
        plan = make_plan(
            bob,
            workouts=[
                {
                    "sport": "cycling" if n % 2 else "running",
                    "title": f"Session {n}",
                }
                for n in range(14)
            ],
        )
        make_activity(bob, "2026-11-09T07:00")
        for hour in range(12):
            make_activity(
                bob, f"2026-11-1{hour % 4}T{hour:02d}:00", rpe=hour % 5 + 1 if hour < 5 else None
            )
        for workout in PlannedWorkout.objects.filter(plan=plan)[:5]:
            WorkoutReview.objects.create(owner=bob, workout=workout, no_activity=True)
        WeekFeedback.objects.create(owner=bob, week_start=MONDAY, fatigue=2)
        WeekComment.objects.create(owner=bob, week_start=MONDAY, comment="Fine.", next_week="hold")
        with CaptureQueriesContext(connection) as large:
            review = week_review(bob, MONDAY)

        assert len(review.workouts) == 14 and len(review.activities) == 13
        assert len(small) == len(large)


class TestWhetherThereIsSomethingToLookBackOn:
    def test_an_empty_week_has_nothing(self, alice: User) -> None:
        assert not has_anything(week_review(alice, MONDAY))

    def test_a_draft_alone_is_nothing(self, alice: User) -> None:
        make_plan(alice, status="draft", workouts=2)

        assert not has_anything(week_review(alice, MONDAY))

    def test_a_confirmed_plan(self, alice: User) -> None:
        make_plan(alice, workouts=1)

        assert has_anything(week_review(alice, MONDAY))

    def test_an_activity(self, alice: User) -> None:
        make_activity(alice, "2026-11-10T07:00")

        assert has_anything(week_review(alice, MONDAY))

    def test_feedback(self, alice: User) -> None:
        WeekFeedback.objects.create(owner=alice, week_start=MONDAY, pain=2)

        assert has_anything(week_review(alice, MONDAY))

    def test_what_belongs_to_another_week_or_user_is_nothing(self, alice: User, bob: User) -> None:
        make_activity(alice, (MONDAY - timedelta(days=2)).isoformat() + "T07:00")
        make_plan(bob, workouts=1)

        assert not has_anything(week_review(alice, MONDAY))


class TestTheSummaryOfAnyWeek:
    def test_a_week_beyond_the_window_of_the_page_can_be_summed_up(self, alice: User) -> None:
        old = MONDAY - timedelta(weeks=REVIEW_WEEKS + 3)
        make_plan(alice, old, workouts=1)
        with pytest.raises(WeekNotReviewable):
            week_review(alice, old)

        summary = week_summary(alice, old)

        assert summary is not None and summary.week_start == old
        assert len(summary.workouts) == 1

    def test_it_is_the_review_of_the_week_otherwise(self, alice: User) -> None:
        make_plan(alice, workouts=2)
        make_activity(alice, "2026-11-09T07:00", rpe=6)

        summary = week_summary(alice, MONDAY)

        assert summary is not None
        assert summary.match == week_review(alice, MONDAY).match
        assert summary.comparison == week_review(alice, MONDAY).comparison

    def test_the_running_week_is_summed_up_too(self, alice: User) -> None:
        make_plan(alice, workouts=7)

        summary = week_summary(alice, MONDAY)

        assert summary is not None
        assert summary.comparison.statuses[Status.OPEN] == 2

    def test_a_week_that_has_not_begun_is_none(self, alice: User) -> None:
        next_week = MONDAY + timedelta(weeks=1)
        make_plan(alice, next_week, workouts=2)

        assert week_summary(alice, next_week) is None

    def test_a_week_with_nothing_in_it_is_none(self, alice: User) -> None:
        assert week_summary(alice, MONDAY - timedelta(weeks=1)) is None

    def test_the_week_is_the_week_of_the_time_zone_of_the_user(
        self, alice: User, bob: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Sunday 23:30 UTC: already next Monday in Berlin, still Sunday in Los Angeles.
        sunday_night = datetime(2026, 11, 15, 23, 30, tzinfo=UTC)
        monkeypatch.setattr(goal_services, "_utc_now", lambda: sunday_night)
        next_week = MONDAY + timedelta(weeks=1)
        for user, zone in ((alice, "Europe/Berlin"), (bob, "America/Los_Angeles")):
            AthleteProfile.objects.create(owner=user, timezone=zone)
            make_plan(user, next_week, workouts=1)

        assert week_summary(alice, next_week) is not None
        assert week_summary(bob, next_week) is None

    def test_a_day_that_is_no_monday_is_refused(self, alice: User) -> None:
        with pytest.raises(ValueError, match="Monday"):
            week_summary(alice, MONDAY + timedelta(days=1))

    def test_the_data_of_another_user_is_not_part_of_it(self, alice: User, bob: User) -> None:
        make_plan(bob, workouts=3)
        make_activity(bob, "2026-11-09T07:00")
        WeekFeedback.objects.create(owner=bob, week_start=MONDAY, pain=5)

        assert week_summary(alice, MONDAY) is None

    def test_it_takes_the_same_number_of_queries_with_or_without_data(self, alice: User) -> None:
        with CaptureQueriesContext(connection) as empty:
            week_summary(alice, MONDAY)
        make_plan(alice, workouts=7)
        for hour in range(5):
            make_activity(alice, f"2026-11-1{hour % 3}T{hour:02d}:00", rpe=4)
        WeekFeedback.objects.create(owner=alice, week_start=MONDAY, fatigue=2)
        WeekComment.objects.create(owner=alice, week_start=MONDAY, comment="x", next_week="hold")
        first = PlannedWorkout.objects.filter(owner=alice).first()
        assert first is not None
        WorkoutReview.objects.create(owner=alice, workout=first, no_activity=True)

        with CaptureQueriesContext(connection) as full:
            week_summary(alice, MONDAY)

        assert len(empty) == len(full)
