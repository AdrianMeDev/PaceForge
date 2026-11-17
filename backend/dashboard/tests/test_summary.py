from datetime import UTC, date, datetime, timedelta

import pytest

from accounts.models import User
from dashboard.summary import week_glance
from goals import services as goal_services
from planning.models import PlannedWorkout, WorkoutExport
from reviews.models import WeekFeedback
from reviews.tests.builders import MONDAY, NOW, make_activity, make_plan

pytestmark = pytest.mark.django_db

NEXT_MONDAY = MONDAY + timedelta(weeks=1)
LAST_MONDAY = MONDAY - timedelta(weeks=1)
SUNDAY = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(goal_services, "_utc_now", lambda: NOW)


def at(monkeypatch: pytest.MonkeyPatch, moment: datetime) -> None:
    monkeypatch.setattr(goal_services, "_utc_now", lambda: moment)


def sync(owner: User, workout: PlannedWorkout, status: str = "synced") -> None:
    WorkoutExport.objects.create(
        owner=owner,
        week_start=workout.plan.week_start,
        workout=workout,
        external_id=f"pf-{workout.pk}",
        status=status,
        event_id=7 if status == "synced" else None,
        error_code="" if status == "synced" else "http_500",
    )


class TestAnEmptyAccount:
    def test_has_nothing_and_nothing_to_close(self, alice: User) -> None:
        glance = week_glance(alice)

        assert glance.week_start == MONDAY
        assert glance.next_workout is None
        assert glance.close_week is None
        assert glance.figures.planned_minutes == 0
        assert glance.figures.done_minutes == 0
        assert glance.figures.workouts_total == 0
        assert glance.figures.average_rpe is None


class TestTheNextWorkout:
    def test_is_the_first_open_one_from_today(self, alice: User) -> None:
        make_plan(alice, workouts=7)  # one run a day, Monday to Sunday; today is the Saturday

        found = week_glance(alice).next_workout

        assert found is not None
        assert found.day == date(2026, 11, 14)
        assert found.title == "Run 5"
        assert found.minutes == 60
        assert found.sent is False

    def test_skips_a_workout_of_today_that_is_done(self, alice: User) -> None:
        make_plan(alice, workouts=7)
        make_activity(alice, "2026-11-14T08:00:00")

        found = week_glance(alice).next_workout

        assert found is not None
        assert found.day == date(2026, 11, 15)

    def test_comes_from_next_week_when_this_week_is_over(self, alice: User) -> None:
        make_plan(alice, workouts=5)  # Monday to Friday: all in the past
        make_plan(alice, NEXT_MONDAY, workouts=2)

        found = week_glance(alice).next_workout

        assert found is not None
        assert found.day == NEXT_MONDAY

    def test_ignores_a_plan_that_is_not_confirmed(self, alice: User) -> None:
        make_plan(alice, status="draft", workouts=7)
        make_plan(alice, NEXT_MONDAY, status="draft", workouts=2)

        assert week_glance(alice).next_workout is None

    def test_says_when_it_is_at_intervals(self, alice: User) -> None:
        make_plan(alice, workouts=7)
        workout = PlannedWorkout.objects.get(owner=alice, day=date(2026, 11, 14))
        sync(alice, workout)

        found = week_glance(alice).next_workout

        assert found is not None
        assert found.sent is True

    def test_a_failed_push_is_not_sent(self, alice: User) -> None:
        make_plan(alice, workouts=7)
        sync(alice, PlannedWorkout.objects.get(owner=alice, day=date(2026, 11, 14)), "failed")

        found = week_glance(alice).next_workout

        assert found is not None
        assert found.sent is False


class TestTheFiguresOfTheWeek:
    def test_count_minutes_and_workouts(self, alice: User) -> None:
        make_plan(alice, workouts=4)
        make_activity(alice, "2026-11-09T08:00:00", rpe=5)
        make_activity(alice, "2026-11-10T08:00:00", rpe=6, timer_seconds=1800.0)
        make_activity(alice, "2026-11-11T08:00:00")

        figures = week_glance(alice).figures

        assert figures.planned_minutes == 240
        assert figures.done_minutes == 60 + 30 + 60
        assert figures.workouts_total == 4
        assert figures.workouts_done == 2  # Tuesday's run is 30 of 60 minutes: partial
        assert figures.average_rpe == 5.5

    def test_leave_out_the_activities_of_other_weeks(self, alice: User) -> None:
        make_activity(alice, "2026-11-08T08:00:00", rpe=9)
        make_activity(alice, "2026-11-16T08:00:00", rpe=9)

        figures = week_glance(alice).figures

        assert figures.done_minutes == 0
        assert figures.average_rpe is None

    def test_do_not_count_another_users_data(self, alice: User, bob: User) -> None:
        make_plan(bob, workouts=7)
        make_activity(bob, "2026-11-09T08:00:00", rpe=8)

        glance = week_glance(alice)

        assert glance.next_workout is None
        assert glance.figures.planned_minutes == 0
        assert glance.figures.average_rpe is None


class TestTheWeekToClose:
    def test_is_this_week_on_a_sunday(self, alice: User, monkeypatch: pytest.MonkeyPatch) -> None:
        make_plan(alice, workouts=3)
        at(monkeypatch, SUNDAY)

        assert week_glance(alice).close_week == MONDAY

    def test_is_not_this_week_before_sunday(self, alice: User) -> None:
        make_plan(alice, workouts=3)

        assert week_glance(alice).close_week is None

    def test_is_not_this_week_once_it_has_feedback(
        self, alice: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        make_plan(alice, workouts=3)
        WeekFeedback.objects.create(owner=alice, week_start=MONDAY, fatigue=3)
        at(monkeypatch, SUNDAY)

        assert week_glance(alice).close_week is None

    def test_is_not_an_empty_week_on_a_sunday(
        self, alice: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        at(monkeypatch, SUNDAY)

        assert week_glance(alice).close_week is None

    def test_is_last_week_when_it_was_not_closed(self, alice: User) -> None:
        make_plan(alice, LAST_MONDAY, workouts=3)

        assert week_glance(alice).close_week == LAST_MONDAY

    def test_is_last_week_by_its_activities_alone(self, alice: User) -> None:
        make_activity(alice, "2026-11-04T08:00:00")

        assert week_glance(alice).close_week == LAST_MONDAY

    def test_is_not_last_week_once_it_has_feedback(self, alice: User) -> None:
        make_plan(alice, LAST_MONDAY, workouts=3)
        WeekFeedback.objects.create(owner=alice, week_start=LAST_MONDAY, fatigue=3)

        assert week_glance(alice).close_week is None

    def test_prefers_this_week_on_a_sunday(
        self, alice: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        make_plan(alice, LAST_MONDAY, workouts=3)
        make_plan(alice, workouts=3)
        at(monkeypatch, SUNDAY)

        assert week_glance(alice).close_week == MONDAY

    def test_does_not_look_at_another_users_weeks(self, alice: User, bob: User) -> None:
        make_plan(bob, LAST_MONDAY, workouts=3)

        assert week_glance(alice).close_week is None
