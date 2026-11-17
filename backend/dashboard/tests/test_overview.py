from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest

from accounts.models import User
from athletes.models import AthleteProfile
from coach.models import AIUsageRecord
from dashboard.overview import CHART_WEEKS, RECENT_ACTIVITIES, dashboard_of
from goals import services as goal_services
from goals.models import Goal
from goals.realism import Rating
from planning.schema import Sport
from reviews.tests.builders import MONDAY, NOW, make_activity
from season import services as season_services
from season.rules import SeasonContext
from season.schema import Focus, KeySession, PlanWeek, SeasonPlan, SessionKind
from season.skeleton import Phase, Race, SkeletonInputs, build_skeleton

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(goal_services, "_utc_now", lambda: NOW)


def confirm_season(user: User, *, confirmed: bool = True) -> None:
    """A season (confirmed, or a draft) whose first week is the week of ``MONDAY``, with a main
    race in it."""
    races = (Race(MONDAY + timedelta(weeks=12, days=6), "main", "running", 10_000, "Race"),)
    skeleton = build_skeleton(SkeletonInputs(MONDAY, (600,) * 52, races, 300, "normal"))
    key = (KeySession(Sport.RUNNING, SessionKind.LONG, 60, "3 x 10 min"),)
    plan = SeasonPlan(
        tuple(
            PlanWeek(
                week.week_start,
                ((Sport.RUNNING, week.target_minutes - 10), (Sport.CYCLING, 10)),
                Focus.THRESHOLD,
                "Why.",
                key if index == 0 else (),
            )
            for index, week in enumerate(skeleton.weeks)
        ),
        "The season.",
    )
    stored = season_services.save_draft(user, plan, SeasonContext(skeleton))
    if confirmed:
        season_services.confirm(user, stored.pk)


def make_goal(owner: User, **fields: Any) -> Goal:
    data: dict[str, Any] = {"kind": "general", "title": "Build endurance", **fields}
    return Goal.objects.create(owner=owner, **data)


def use_coach(owner: User, **fields: Any) -> None:
    data: dict[str, Any] = {
        "provider": "anthropic",
        "model": "m",
        "purpose": "check",
        "outcome": "success",
        "input_tokens": 10,
        "output_tokens": 4,
        **fields,
    }
    AIUsageRecord.objects.create(owner=owner, **data)


class TestAnEmptyAccount:
    def test_has_an_empty_block_everywhere(self, alice: User) -> None:
        found = dashboard_of(alice)

        assert found.season is None
        assert found.main_goal is None
        assert found.recent == ()
        assert found.usage.calls == 0
        assert [week.week_start for week in found.weeks] == [
            MONDAY - timedelta(weeks=n) for n in range(CHART_WEEKS - 1, -1, -1)
        ]
        assert all(week.sports == () for week in found.weeks)


class TestTheSeason:
    def test_is_the_week_in_the_confirmed_plan(self, alice: User) -> None:
        confirm_season(alice)

        found = dashboard_of(alice).season

        assert found is not None
        assert found.phase is Phase.BASE
        assert found.recovery is False
        assert found.target_minutes > 0

    def test_is_missing_for_a_draft(self, alice: User) -> None:
        confirm_season(alice, confirmed=False)

        assert dashboard_of(alice).season is None


class TestTheMainGoal:
    def test_is_judged_and_counts_the_weeks(self, alice: User) -> None:
        make_goal(
            alice,
            kind="race",
            title="My 10k",
            priority="main",
            discipline="running",
            distance_m=10_000,
            target_time_seconds=3000,
            target_date=date(2027, 1, 2),
        )

        found = dashboard_of(alice).main_goal

        assert found is not None
        assert found.title == "My 10k"
        assert found.weeks_left == 7  # 49 days from the 14th of November
        assert found.assessment.rating is Rating.UNKNOWN  # no best time yet

    def test_without_a_date_has_no_weeks(self, alice: User) -> None:
        make_goal(alice, priority="main")

        found = dashboard_of(alice).main_goal

        assert found is not None
        assert found.weeks_left is None

    def test_with_a_date_that_has_passed_has_no_weeks(self, alice: User) -> None:
        make_goal(alice, priority="main", target_date=date(2026, 11, 1))

        found = dashboard_of(alice).main_goal

        assert found is not None
        assert found.weeks_left is None

    def test_is_not_a_goal_that_is_secondary_or_not_active(self, alice: User) -> None:
        make_goal(alice, title="B", priority="secondary")
        make_goal(alice, title="Old", priority="main", status="achieved")

        assert dashboard_of(alice).main_goal is None

    def test_is_not_another_users_goal(self, alice: User, bob: User) -> None:
        make_goal(bob, priority="main")

        assert dashboard_of(alice).main_goal is None


class TestTheLastWeeks:
    def test_add_up_the_minutes_per_sport(self, alice: User) -> None:
        make_activity(alice, "2026-11-10T08:00:00")
        make_activity(alice, "2026-11-11T08:00:00", sport="cycling", timer_seconds=1800.0)
        make_activity(alice, "2026-11-03T08:00:00")

        weeks = {week.week_start: week.sports for week in dashboard_of(alice).weeks}

        assert weeks[MONDAY] == (("running", 60), ("cycling", 30))
        assert weeks[MONDAY - timedelta(weeks=1)] == (("running", 60),)
        assert weeks[MONDAY - timedelta(weeks=2)] == ()

    def test_stop_after_eight_weeks(self, alice: User) -> None:
        make_activity(alice, "2026-09-14T08:00:00")  # nine weeks back: not on the chart
        make_activity(alice, "2026-09-21T08:00:00")  # eight weeks back: the first one

        weeks = dashboard_of(alice).weeks

        assert len(weeks) == CHART_WEEKS
        assert weeks[0].week_start == date(2026, 9, 21)
        assert weeks[0].sports == (("running", 60),)

    def test_leave_out_another_users_minutes(self, alice: User, bob: User) -> None:
        make_activity(bob, "2026-11-10T08:00:00")

        assert all(week.sports == () for week in dashboard_of(alice).weeks)


class TestTheLatestActivities:
    def test_are_the_last_three_newest_first(self, alice: User) -> None:
        for day in range(1, 6):
            make_activity(alice, f"2026-11-0{day}T08:00:00")

        found = dashboard_of(alice).recent

        assert len(found) == RECENT_ACTIVITIES
        assert [item.day for item in found] == [
            date(2026, 11, 5),
            date(2026, 11, 4),
            date(2026, 11, 3),
        ]

    def test_are_on_the_day_of_the_athlete(self, alice: User) -> None:
        AthleteProfile.objects.create(owner=alice, timezone="Australia/Sydney")
        make_activity(alice, "2026-11-12T20:00:00")  # the 13th in Sydney

        found = dashboard_of(alice).recent

        assert found[0].day == date(2026, 11, 13)

    def test_use_the_elapsed_time_without_a_timer_and_none_without_either(
        self, alice: User
    ) -> None:
        make_activity(alice, "2026-11-12T08:00:00", timer_seconds=None, elapsed_seconds=1800.0)
        make_activity(alice, "2026-11-13T08:00:00", timer_seconds=None, elapsed_seconds=None)

        found = dashboard_of(alice).recent

        assert [item.minutes for item in found] == [None, 30]

    def test_leave_out_another_users_activities(self, alice: User, bob: User) -> None:
        make_activity(bob, "2026-11-12T08:00:00")

        assert dashboard_of(alice).recent == ()


class TestTheCoachUsage:
    def test_adds_up_the_calls(self, alice: User) -> None:
        use_coach(alice)
        use_coach(alice, outcome="rate_limited", input_tokens=5, output_tokens=None)

        found = dashboard_of(alice).usage

        assert (found.calls, found.input_tokens, found.output_tokens) == (2, 15, 4)
        assert found.days == 30

    def test_leave_out_another_users_calls(self, alice: User, bob: User) -> None:
        use_coach(bob)

        assert dashboard_of(alice).usage.calls == 0


def test_the_clock_is_the_one_of_the_tests() -> None:
    assert NOW == datetime(2026, 11, 14, 12, 0, tzinfo=UTC)
