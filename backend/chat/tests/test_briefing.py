from datetime import date
from typing import Any

import pytest

from accounts.models import User
from availability.models import AvailabilitySettings
from chat.briefing import KEPT, build_briefing
from goals import services as goal_services
from planning import services as plan_services
from reviews.tests.builders import MONDAY, NOW, make_plan

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(goal_services, "_utc_now", lambda: NOW)


def briefing_of(user: User, workouts: int = 3) -> dict[str, Any]:
    stored = make_plan(user, MONDAY, workouts=workouts, status="draft")
    return build_briefing(user, plan_services.load(user, stored.pk))


class TestTheBriefing:
    def test_holds_what_the_chat_needs_and_the_workouts(self, alice: User) -> None:
        data = briefing_of(alice)

        assert set(data) == {*KEPT, "workouts"}
        assert data["week_start"] == MONDAY.isoformat()
        assert data["today"] == NOW.date().isoformat()
        assert len(data["workouts"]) == 3

    def test_a_workout_carries_the_id_the_coach_names_and_whether_it_can_change(
        self, alice: User
    ) -> None:
        stored = make_plan(alice, MONDAY, workouts=3, status="draft")
        plan = plan_services.load(alice, stored.pk)

        data = build_briefing(alice, plan)

        ids = {workout["id"] for workout in data["workouts"]}
        assert ids == {str(workout.lineage) for workout in plan.workouts}
        today = date.fromisoformat(data["today"])
        for workout in data["workouts"]:
            assert workout["changeable"] == (date.fromisoformat(workout["day"]) >= today)
        assert {"id", "day", "slot", "sport", "title", "minutes", "changeable"} <= set(
            data["workouts"][0]
        )

    def test_has_nothing_of_another_user(self, alice: User, bob: User) -> None:
        AvailabilitySettings.objects.create(owner=bob, limitations="Bob's secret knee")
        make_plan(bob, MONDAY, workouts=5)

        text = str(briefing_of(alice))

        assert "Bob's secret knee" not in text

    def test_the_free_text_about_limitations_goes_only_with_the_switch(self, alice: User) -> None:
        AvailabilitySettings.objects.create(owner=alice, limitations="Sore knee")

        assert briefing_of(alice)["limitations_text"] is None

        AvailabilitySettings.objects.filter(owner=alice).update(share_limitations_text=True)

        assert briefing_of(alice)["limitations_text"] == "Sore knee"
