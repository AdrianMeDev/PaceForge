import json
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from typing import Any

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from accounts.models import User
from accounts.tests.conftest import AuthApi
from athletes.models import AthleteProfile
from goals import services as goal_services
from planning.models import PlannedWorkout
from reviews.models import WeekFeedback, WorkoutReview

from .builders import MONDAY, NOW, make_activity, make_plan
from .conftest import make_user, signed_in

pytestmark = pytest.mark.django_db

WEEKS = "/api/reviews/weeks/"
MARKER = "SECRETMARKER"


def week_url(monday: Any = MONDAY) -> str:
    return f"{WEEKS}{monday}/"


@pytest.fixture(autouse=True)
def _clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(goal_services, "_utc_now", lambda: NOW)


@pytest.fixture
def alice() -> User:
    return make_user("alice@example.com")


@pytest.fixture
def bob() -> User:
    return make_user("bob@example.com")


def get(user: User, url: str) -> Any:
    return signed_in(user).call("GET", url)


def body(response: Any) -> Any:
    return json.loads(response.content)


class TestTheWeeks:
    def test_the_current_week_and_four_before_it_oldest_first(self, alice: User) -> None:
        response = get(alice, WEEKS)

        assert response.status_code == HTTPStatus.OK
        weeks = body(response)["weeks"]
        assert [week["week_start"] for week in weeks] == [
            (MONDAY - timedelta(weeks=n)).isoformat() for n in (4, 3, 2, 1, 0)
        ]
        assert all(
            set(week) == {"week_start", "has_plan", "workout_count", "has_feedback"}
            for week in weeks
        )
        assert not any(week["has_plan"] or week["has_feedback"] for week in weeks)

    def test_a_week_with_a_confirmed_plan_and_one_with_feedback(self, alice: User) -> None:
        make_plan(alice, workouts=3)
        before = MONDAY - timedelta(weeks=2)
        WeekFeedback.objects.create(owner=alice, week_start=before, fatigue=2)

        weeks = {week["week_start"]: week for week in body(get(alice, WEEKS))["weeks"]}

        assert weeks[MONDAY.isoformat()] == {
            "week_start": MONDAY.isoformat(),
            "has_plan": True,
            "workout_count": 3,
            "has_feedback": False,
        }
        assert weeks[before.isoformat()]["has_feedback"] is True
        assert weeks[before.isoformat()]["has_plan"] is False

    def test_a_draft_or_a_superseded_plan_is_no_plan_to_review(self, alice: User) -> None:
        make_plan(alice, status="superseded", workouts=2)
        make_plan(alice, status="draft", workouts=2)

        week = body(get(alice, WEEKS))["weeks"][-1]

        assert (week["has_plan"], week["workout_count"]) == (False, 0)

    def test_other_users_data_is_not_shown(self, alice: User, bob: User) -> None:
        make_plan(bob, workouts=3)
        WeekFeedback.objects.create(owner=bob, week_start=MONDAY, pain=4)

        week = body(get(alice, WEEKS))["weeks"][-1]

        assert (week["has_plan"], week["has_feedback"]) == (False, False)

    def test_the_week_depends_on_the_time_zone_of_the_user(
        self, alice: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            goal_services, "_utc_now", lambda: datetime(2026, 11, 15, 23, 30, tzinfo=UTC)
        )
        AthleteProfile.objects.create(owner=alice, timezone="Europe/Berlin")

        last = body(get(alice, WEEKS))["weeks"][-1]["week_start"]

        assert last == (MONDAY + timedelta(days=7)).isoformat()

    def test_it_takes_the_same_number_of_queries_however_much_data_there_is(
        self, alice: User
    ) -> None:
        api = signed_in(alice)
        with CaptureQueriesContext(connection) as empty:
            api.call("GET", WEEKS)
        for weeks_back in range(5):
            monday = MONDAY - timedelta(weeks=weeks_back)
            make_plan(alice, monday, workouts=4)
            WeekFeedback.objects.create(owner=alice, week_start=monday)
        with CaptureQueriesContext(connection) as full:
            api.call("GET", WEEKS)

        assert len(empty) == len(full)


class TestOneWeek:
    def test_a_week_without_a_plan_shows_its_activities_as_not_planned(self, alice: User) -> None:
        activity = make_activity(alice, "2026-11-10T07:00", rpe=5, notes="easy")

        data = body(get(alice, week_url()))

        assert data["week_start"] == MONDAY.isoformat()
        assert data["today"] == "2026-11-14"
        assert data["plan"] is None
        assert data["workouts"] == []
        assert data["feedback"] is None
        (shown,) = data["activities"]
        assert shown["id"] == str(activity.pk)
        assert shown["workout_id"] is None
        assert (shown["day"], shown["rpe"], shown["notes"]) == ("2026-11-10", 5, "easy")

    def test_the_plan_the_match_the_comparison_and_the_feedback(self, alice: User) -> None:
        plan = make_plan(alice, workouts=2)
        run = make_activity(alice, "2026-11-09T07:00", rpe=6)
        extra = make_activity(alice, "2026-11-12T18:00", sport="strength", timer_seconds=1800.0)
        WeekFeedback.objects.create(
            owner=alice, week_start=MONDAY, fatigue=4, motivation=2, pain=1, notes="Tired"
        )

        data = body(get(alice, week_url()))

        assert data["plan"]["id"] == str(plan.pk)
        first, second = data["workouts"]
        assert (first["title"], first["status"], first["status_origin"]) == (
            "Run 0",
            "done",
            "auto",
        )
        assert (first["activity_id"], first["activity_origin"]) == (str(run.pk), "auto")
        assert (second["status"], second["activity_id"], second["activity_origin"]) == (
            "missed",
            None,
            None,
        )
        by_id = {activity["id"]: activity for activity in data["activities"]}
        assert by_id[str(run.pk)]["workout_id"] == first["id"]
        assert by_id[str(extra.pk)]["workout_id"] is None
        assert data["comparison"]["statuses"] == {
            "done": 1,
            "partial": 0,
            "missed": 1,
            "replaced": 0,
            "open": 0,
        }
        assert data["comparison"]["done_percent"] == 50
        running = next(
            sport for sport in data["comparison"]["sports"] if sport["sport"] == "running"
        )
        assert running == {
            "sport": "running",
            "planned_count": 2,
            "planned_minutes": 120,
            "actual_count": 1,
            "actual_minutes": 60,
            "load": 360,
            "rated_count": 1,
        }
        assert data["comparison"]["total"]["actual_count"] == 2
        assert {
            key: data["feedback"][key] for key in ("fatigue", "motivation", "pain", "notes")
        } == {
            "fatigue": 4,
            "motivation": 2,
            "pain": 1,
            "notes": "Tired",
        }

    def test_titles_and_notes_are_shown_as_stored(self, alice: User) -> None:
        plan = make_plan(alice, workouts=1)
        PlannedWorkout.objects.filter(plan=plan).update(
            title="<b>Hills</b>", notes='"quoted" & more'
        )

        (workout,) = body(get(alice, week_url()))["workouts"]

        assert (workout["title"], workout["notes"]) == ("<b>Hills</b>", '"quoted" & more')

    def test_what_the_user_decided_is_shown(self, alice: User) -> None:
        plan = make_plan(alice, workouts=2)
        run = make_activity(alice, "2026-11-09T07:00")
        first, second = plan.workouts.all()
        WorkoutReview.objects.create(owner=alice, workout=first, status="missed")
        WorkoutReview.objects.create(owner=alice, workout=second, activity=run, status="partial")

        one, two = body(get(alice, week_url()))["workouts"]

        assert (one["status"], one["status_origin"], one["activity_id"]) == ("missed", "user", None)
        assert one["activity_origin"] == "user"
        assert (two["status"], two["status_origin"], two["activity_id"]) == (
            "partial",
            "user",
            str(run.pk),
        )
        assert two["activity_origin"] == "user"

    def test_a_workout_that_is_open_is_still_to_come(self, alice: User) -> None:
        make_plan(alice, workouts=7)  # one a day; the clock is on Saturday

        statuses = [workout["status"] for workout in body(get(alice, week_url()))["workouts"]]

        assert statuses == ["missed"] * 5 + ["open"] * 2

    def test_another_users_plan_and_activities_are_not_shown(self, alice: User, bob: User) -> None:
        make_plan(bob, workouts=2)
        make_activity(bob, "2026-11-09T07:00", notes=MARKER)
        WeekFeedback.objects.create(owner=bob, week_start=MONDAY, notes=MARKER)

        response = get(alice, week_url())

        assert response.status_code == HTTPStatus.OK
        assert MARKER not in response.content.decode()
        assert body(response)["plan"] is None

    def test_no_owner_hash_or_file_is_part_of_an_activity(self, alice: User) -> None:
        make_activity(alice, "2026-11-09T07:00", source="fit_file", source_hash="a" * 64)

        (activity,) = body(get(alice, week_url()))["activities"]

        assert "owner" not in activity and "source_hash" not in activity and "laps" not in activity

    def test_it_takes_the_same_number_of_queries_however_much_data_there_is(
        self, alice: User
    ) -> None:
        api = signed_in(alice)
        plan = make_plan(alice, workouts=1)
        make_activity(alice, "2026-11-09T07:00")
        with CaptureQueriesContext(connection) as small:
            api.call("GET", week_url())
        PlannedWorkout.objects.bulk_create(
            PlannedWorkout(
                owner=alice,
                plan=plan,
                day=MONDAY + timedelta(days=n % 7),
                position=n // 7,
                sport="cycling",
                title="Ride",
                goal="endurance",
                duration_minutes=60,
            )
            for n in range(1, 10)
        )
        for hour in range(10):
            make_activity(alice, f"2026-11-1{hour % 4}T{hour:02d}:30", rpe=4)
        with CaptureQueriesContext(connection) as large:
            api.call("GET", week_url())

        assert len(small) == len(large)


class TestRefusals:
    @pytest.mark.parametrize(
        "week",
        [
            "2026-11-10",  # a Tuesday
            "2026-11-16",  # next week
            "2026-10-05",  # more than four weeks back
            "2026-02-30",
            "2026-13-01",
            "not-a-date",
            "20261109",
            "2026-11-9",
            "2026-11-09x",
        ],
    )
    def test_a_week_that_cannot_be_reviewed_is_a_404_with_a_fixed_text(
        self, alice: User, week: str
    ) -> None:
        response = get(alice, f"{WEEKS}{week}/")

        assert response.status_code == HTTPStatus.NOT_FOUND
        assert body(response) == {
            "detail": "This week cannot be reviewed.",
            "code": "week_not_reviewable",
        }

    def test_nothing_of_the_request_is_repeated(self, alice: User) -> None:
        response = get(alice, f"{WEEKS}{MARKER}/")

        assert response.status_code == HTTPStatus.NOT_FOUND
        assert MARKER not in response.content.decode()

    @pytest.mark.parametrize("url", [WEEKS, week_url()])
    def test_anonymous_visitors_are_refused(self, url: str) -> None:
        assert AuthApi().call("GET", url).status_code == HTTPStatus.FORBIDDEN

    @pytest.mark.parametrize("url", [WEEKS, week_url()])
    @pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
    def test_these_are_read_only(self, alice: User, url: str, method: str) -> None:
        response = signed_in(alice).call(method, url, {})

        assert response.status_code == HTTPStatus.METHOD_NOT_ALLOWED
