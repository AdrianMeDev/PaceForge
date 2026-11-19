from datetime import date, timedelta
from typing import Any

import pytest

from accounts.models import User
from availability.models import AvailabilitySettings, UnavailablePeriod
from chat.briefing import KEPT, WEEK_KEPT, build_briefing
from goals import services as goal_services
from planning import services as plan_services
from planning.models import PlannedWorkout
from reviews.tests.builders import MONDAY, NOW, make_plan

pytestmark = pytest.mark.django_db

NEXT_MONDAY = MONDAY + timedelta(days=7)


@pytest.fixture(autouse=True)
def _clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(goal_services, "_utc_now", lambda: NOW)


def briefing_of(user: User, workouts: int = 3) -> dict[str, Any]:
    stored = make_plan(user, MONDAY, workouts=workouts, status="draft")
    return build_briefing(user, [plan_services.load(user, stored.pk)])


class TestTheBriefing:
    def test_holds_what_the_chat_needs_and_the_weeks(self, alice: User) -> None:
        data = briefing_of(alice)

        assert set(data) == {*KEPT, "weeks"}
        assert data["today"] == NOW.date().isoformat()
        (week,) = data["weeks"]
        assert set(week) == {*WEEK_KEPT, "workouts"}
        assert week["week_start"] == MONDAY.isoformat()
        assert len(week["days"]) == 7
        assert len(week["workouts"]) == 3

    def test_a_workout_carries_the_id_the_coach_names_and_whether_it_can_change(
        self, alice: User
    ) -> None:
        stored = make_plan(alice, MONDAY, workouts=3, status="draft")
        plan = plan_services.load(alice, stored.pk)

        data = build_briefing(alice, [plan])

        (week,) = data["weeks"]
        ids = {workout["id"] for workout in week["workouts"]}
        assert ids == {str(workout.lineage) for workout in plan.workouts}
        today = date.fromisoformat(data["today"])
        for workout in week["workouts"]:
            assert workout["changeable"] == (date.fromisoformat(workout["day"]) >= today)
        assert {"id", "day", "slot", "sport", "title", "minutes", "changeable"} <= set(
            week["workouts"][0]
        )

    def test_lists_two_weeks_in_order_with_their_own_days_and_workouts(self, alice: User) -> None:
        this_stored = make_plan(alice, MONDAY, workouts=7, status="confirmed")
        next_stored = make_plan(alice, NEXT_MONDAY, workouts=2, status="draft")
        UnavailablePeriod.objects.create(
            owner=alice,
            kind=UnavailablePeriod.Kind.VACATION,
            start_date=NEXT_MONDAY + timedelta(days=2),
            end_date=NEXT_MONDAY + timedelta(days=2),
        )
        this_plan = plan_services.load(alice, this_stored.pk)
        next_plan = plan_services.load(alice, next_stored.pk)

        data = build_briefing(alice, [next_plan, this_plan])

        assert [week["week_start"] for week in data["weeks"]] == [
            MONDAY.isoformat(),
            NEXT_MONDAY.isoformat(),
        ]
        first, second = data["weeks"]
        assert len(first["workouts"]) == 7
        assert len(second["workouts"]) == 2
        assert first["days"][0]["date"] == MONDAY.isoformat()
        assert second["days"][0]["date"] == NEXT_MONDAY.isoformat()
        assert all(day["absence"] is None for day in first["days"])
        assert second["days"][2]["absence"] == "vacation"
        assert all(workout["changeable"] for workout in second["workouts"])
        assert not first["workouts"][0]["changeable"]

    def test_without_plans_has_no_weeks(self, alice: User) -> None:
        data = build_briefing(alice, [])

        assert set(data) == {*KEPT, "weeks"}
        assert data["today"] == NOW.date().isoformat()
        assert data["weeks"] == []

    def test_has_nothing_of_another_user(self, alice: User, bob: User) -> None:
        AvailabilitySettings.objects.create(owner=bob, limitations="Bob's secret knee")
        make_plan(bob, MONDAY, workouts=5)
        bob_next = make_plan(bob, NEXT_MONDAY, workouts=4)

        text = str(briefing_of(alice))

        assert "Bob's secret knee" not in text
        assert NEXT_MONDAY.isoformat() not in text
        for workout in PlannedWorkout.objects.for_user(bob).filter(plan=bob_next):
            assert str(workout.lineage) not in text

    def test_the_free_text_about_limitations_goes_only_with_the_switch(self, alice: User) -> None:
        AvailabilitySettings.objects.create(owner=alice, limitations="Sore knee")

        assert briefing_of(alice)["limitations_text"] is None

        AvailabilitySettings.objects.filter(owner=alice).update(share_limitations_text=True)

        assert briefing_of(alice)["limitations_text"] == "Sore knee"
