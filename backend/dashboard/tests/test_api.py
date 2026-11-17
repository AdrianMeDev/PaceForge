import json
from datetime import timedelta
from http import HTTPStatus
from typing import Any

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from accounts.models import User
from accounts.tests.conftest import AuthApi
from goals import services as goal_services
from goals.models import Goal
from reviews.tests.builders import MONDAY, NOW, make_activity, make_plan
from reviews.tests.conftest import make_user, signed_in

from .test_overview import confirm_season, use_coach

pytestmark = pytest.mark.django_db

URL = "/api/dashboard/"


@pytest.fixture(autouse=True)
def _clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(goal_services, "_utc_now", lambda: NOW)


def get(user: User) -> Any:
    return signed_in(user).call("GET", URL)


def body(response: Any) -> Any:
    return json.loads(response.content)


class TestWhoMayAsk:
    def test_a_visitor_is_refused(self) -> None:
        assert AuthApi().call("GET", URL).status_code == HTTPStatus.FORBIDDEN

    @pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
    def test_nothing_can_be_changed(self, alice: User, method: str) -> None:
        assert signed_in(alice).call(method, URL, {}).status_code == HTTPStatus.METHOD_NOT_ALLOWED


class TestTheAnswer:
    def test_for_an_empty_account(self, alice: User) -> None:
        response = get(alice)

        assert response.status_code == HTTPStatus.OK
        assert body(response) == {
            "week": {
                "week_start": MONDAY.isoformat(),
                "next_workout": None,
                "figures": {
                    "planned_minutes": 0,
                    "done_minutes": 0,
                    "workouts_done": 0,
                    "workouts_total": 0,
                    "average_rpe": None,
                },
                "close_week": None,
            },
            "season": None,
            "main_goal": None,
            "weeks": [
                {"week_start": (MONDAY - timedelta(weeks=n)).isoformat(), "sports": []}
                for n in range(7, -1, -1)
            ],
            "recent": [],
            "usage": {"calls": 0, "input_tokens": 0, "output_tokens": 0, "days": 30},
        }

    def test_for_an_account_with_data(self, alice: User) -> None:
        make_plan(alice, workouts=7)
        make_activity(alice, "2026-11-10T08:00:00", rpe=6)
        confirm_season(alice)
        Goal.objects.create(owner=alice, kind="general", title="My goal", priority="main")
        use_coach(alice)

        data = body(get(alice))

        assert data["week"]["next_workout"]["day"] == "2026-11-14"
        assert data["week"]["next_workout"]["sent"] is False
        assert data["week"]["figures"]["done_minutes"] == 60
        assert data["week"]["figures"]["average_rpe"] == 6.0
        assert data["season"]["phase"] == "base"
        assert data["main_goal"]["title"] == "My goal"
        assert data["main_goal"]["assessment"]["rating"] == "unknown"
        assert data["weeks"][-1]["sports"] == [{"sport": "running", "minutes": 60}]
        assert [item["day"] for item in data["recent"]] == ["2026-11-10"]
        assert data["usage"]["calls"] == 1

    def test_has_only_the_data_of_the_user(self, alice: User, bob: User) -> None:
        make_plan(bob, workouts=7)
        make_plan(bob, MONDAY - timedelta(weeks=1), workouts=3)
        make_activity(bob, "2026-11-10T08:00:00", rpe=6)
        Goal.objects.create(owner=bob, kind="general", title="Bob's goal", priority="main")
        use_coach(bob)

        carol = make_user("carol@example.com")  # nothing of her own, like Alice

        assert body(get(alice)) == body(get(carol))
        assert body(get(bob)) != body(get(alice))

    def test_says_which_week_to_close(self, alice: User) -> None:
        make_plan(alice, MONDAY - timedelta(weeks=1), workouts=3)

        assert body(get(alice))["week"]["close_week"] == (MONDAY - timedelta(weeks=1)).isoformat()


class TestTheNumberOfQueries:
    def test_does_not_depend_on_the_data(self, alice: User) -> None:
        api = signed_in(alice)
        with CaptureQueriesContext(connection) as empty:
            assert api.call("GET", URL).status_code == HTTPStatus.OK

        confirm_season(alice)
        for number in range(5):
            make_plan(alice, MONDAY + timedelta(weeks=number - 1), workouts=7)
            make_activity(alice, f"2026-11-0{number + 1}T08:00:00", rpe=5)
            use_coach(alice)
        Goal.objects.create(owner=alice, kind="general", title="Goal", priority="main")
        Goal.objects.create(owner=alice, kind="general", title="Other", priority="secondary")

        with CaptureQueriesContext(connection) as full:
            assert api.call("GET", URL).status_code == HTTPStatus.OK

        assert len(empty) == len(full)
