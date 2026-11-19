import json
from datetime import UTC, date, datetime, timedelta
from http import HTTPStatus
from typing import Any

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from accounts.models import User
from accounts.tests.conftest import AuthApi
from availability.models import UnavailablePeriod, WeekdayMinutes
from goals import services
from goals.models import Goal

from .conftest import make_user, signed_in

pytestmark = pytest.mark.django_db

URL = "/api/season/"
NOW = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)
MONDAY = date(2026, 11, 16)
WEEK_FIELDS = {
    "week_start",
    "phase",
    "recovery",
    "target_minutes",
    "capacity_minutes",
    "races",
}
RACE_FIELDS = {"date", "priority", "discipline", "distance_m", "title"}


@pytest.fixture(autouse=True)
def _fixed_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(services, "_utc_now", lambda: NOW)


@pytest.fixture
def alice() -> User:
    return make_user("alice@example.com")


@pytest.fixture
def bob() -> User:
    return make_user("bob@example.com")


def body(response: Any) -> Any:
    return json.loads(response.content)


def train(user: User, minutes: int = 60) -> None:
    for weekday in range(7):
        WeekdayMinutes.objects.create(owner=user, weekday=weekday, minutes=minutes)


def race(owner: User, weeks: int, priority: str = "main", **fields: Any) -> Goal:
    data: dict[str, Any] = {
        "kind": "race",
        "title": "Berlin Marathon",
        "priority": priority,
        "target_date": MONDAY + timedelta(weeks=weeks, days=6),
        "discipline": "running",
        "distance_m": 42195,
        **fields,
    }
    return Goal.objects.create(owner=owner, **data)


class TestWhoMayCome:
    def test_a_visitor_who_is_not_signed_in_is_refused(self) -> None:
        response = AuthApi().call("GET", URL)

        assert response.status_code == HTTPStatus.FORBIDDEN

    @pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
    def test_nothing_can_be_written(self, alice: User, method: str) -> None:
        response = signed_in(alice).call(method, URL, {"weeks": []})

        assert response.status_code == HTTPStatus.METHOD_NOT_ALLOWED


class TestTheAnswer:
    def test_a_user_with_nothing_gets_the_rolling_skeleton(self, alice: User) -> None:
        response = signed_in(alice).call("GET", URL)

        assert response.status_code == HTTPStatus.OK
        data = body(response)
        assert set(data) == {
            "rolling",
            "truncated",
            "main_race",
            "peak_minutes",
            "weeks",
            "absences",
        }
        assert data["absences"] == []
        assert (data["rolling"], data["truncated"], data["main_race"]) == (True, False, None)
        assert len(data["weeks"]) == 12
        assert data["peak_minutes"] == 0

    def test_a_user_with_a_race_gets_the_weeks_up_to_it(self, alice: User) -> None:
        train(alice)
        race(alice, 14)

        data = body(signed_in(alice).call("GET", URL))

        assert data["rolling"] is False
        assert len(data["weeks"]) == 15
        assert data["main_race"] == {
            "date": "2027-02-28",
            "priority": "main",
            "discipline": "running",
            "distance_m": 42195,
            "title": "Berlin Marathon",
        }
        first, last = data["weeks"][0], data["weeks"][-1]
        assert set(first) == WEEK_FIELDS
        assert first["week_start"] == "2026-11-16"
        assert (last["phase"], last["week_start"]) == ("taper", "2027-02-22")
        assert [set(r) for r in last["races"]] == [RACE_FIELDS]
        assert last["races"][0]["title"] == "Berlin Marathon"
        assert data["peak_minutes"] == max(w["target_minutes"] for w in data["weeks"])

    def test_the_phases_and_the_recovery_flags_are_fixed_words_and_booleans(
        self, alice: User
    ) -> None:
        train(alice)
        race(alice, 20)

        weeks = body(signed_in(alice).call("GET", URL))["weeks"]

        assert {w["phase"] for w in weeks} <= {"base", "build", "specific", "taper", "transition"}
        assert all(isinstance(w["recovery"], bool) for w in weeks)
        assert any(w["recovery"] for w in weeks)

    def test_a_race_beyond_a_year_says_that_it_is_cut_off(self, alice: User) -> None:
        train(alice)
        race(alice, 80)

        data = body(signed_in(alice).call("GET", URL))

        assert data["truncated"] is True
        assert len(data["weeks"]) == 52

    def test_a_race_without_a_distance_has_null_for_it(self, alice: User) -> None:
        race(alice, 5, distance_m=None)

        data = body(signed_in(alice).call("GET", URL))

        assert data["main_race"]["distance_m"] is None

    def test_it_stores_nothing(self, alice: User) -> None:
        train(alice)
        race(alice, 14)
        before = (Goal.objects.count(), WeekdayMinutes.objects.count())

        signed_in(alice).call("GET", URL)

        assert (Goal.objects.count(), WeekdayMinutes.objects.count()) == before

    def test_it_asks_the_database_the_same_number_of_times_for_any_season(
        self, alice: User, bob: User
    ) -> None:
        api = signed_in(alice)
        api.call("GET", URL)  # the session and the cache are warm now
        with CaptureQueriesContext(connection) as empty:
            api.call("GET", URL)
        train(alice)
        for weeks in (5, 10, 20, 30):
            race(alice, weeks, "secondary")

        with CaptureQueriesContext(connection) as full:
            api.call("GET", URL)

        assert len(empty) == len(full)


class TestAbsences:
    def test_an_illness_in_the_weeks_is_listed(self, alice: User) -> None:
        UnavailablePeriod.objects.create(
            owner=alice,
            kind="illness",
            start_date=MONDAY + timedelta(days=2),
            end_date=MONDAY + timedelta(days=5),
        )

        absences = body(signed_in(alice).call("GET", URL))["absences"]

        assert absences == [
            {"kind": "illness", "start_date": "2026-11-18", "end_date": "2026-11-21"}
        ]

    def test_a_period_outside_the_weeks_is_not_listed(self, alice: User) -> None:
        UnavailablePeriod.objects.create(
            owner=alice,
            kind="vacation",
            start_date=MONDAY + timedelta(weeks=40),
            end_date=MONDAY + timedelta(weeks=40, days=6),
        )
        UnavailablePeriod.objects.create(
            owner=alice,
            kind="other",
            start_date=MONDAY - timedelta(days=30),
            end_date=MONDAY - timedelta(days=20),
        )

        assert body(signed_in(alice).call("GET", URL))["absences"] == []

    def test_the_last_day_of_the_last_week_still_counts(self, alice: User) -> None:
        last_day = MONDAY + timedelta(weeks=11, days=6)
        UnavailablePeriod.objects.create(
            owner=alice, kind="illness", start_date=last_day, end_date=last_day
        )

        absences = body(signed_in(alice).call("GET", URL))["absences"]

        assert [a["start_date"] for a in absences] == ["2027-02-07"]

    def test_the_note_of_the_absence_is_not_in_the_answer(self, alice: User) -> None:
        UnavailablePeriod.objects.create(
            owner=alice,
            kind="illness",
            start_date=MONDAY,
            end_date=MONDAY,
            note="a private note",
        )

        text = signed_in(alice).call("GET", URL).content.decode()

        assert "private note" not in text

    def test_the_absences_are_by_start_date(self, alice: User) -> None:
        UnavailablePeriod.objects.create(
            owner=alice,
            kind="illness",
            start_date=MONDAY + timedelta(weeks=5),
            end_date=MONDAY + timedelta(weeks=5),
        )
        UnavailablePeriod.objects.create(
            owner=alice,
            kind="vacation",
            start_date=MONDAY + timedelta(weeks=2),
            end_date=MONDAY + timedelta(weeks=2, days=3),
        )

        absences = body(signed_in(alice).call("GET", URL))["absences"]

        assert [a["kind"] for a in absences] == ["vacation", "illness"]

    def test_the_answer_asks_the_database_one_more_time_for_any_number_of_absences(
        self, alice: User
    ) -> None:
        api = signed_in(alice)
        api.call("GET", URL)  # the session and the cache are warm now
        with CaptureQueriesContext(connection) as empty:
            api.call("GET", URL)
        for week in range(1, 9):
            UnavailablePeriod.objects.create(
                owner=alice,
                kind="illness",
                start_date=MONDAY + timedelta(weeks=week),
                end_date=MONDAY + timedelta(weeks=week),
            )

        with CaptureQueriesContext(connection) as full:
            api.call("GET", URL)

        assert len(full) == len(empty)


class TestIsolation:
    def test_the_data_of_another_user_is_not_in_the_answer(self, alice: User, bob: User) -> None:
        train(bob, 600)
        race(bob, 10, title="Bob's secret race")

        text = signed_in(alice).call("GET", URL).content.decode()

        assert "secret" not in text
        assert body(signed_in(alice).call("GET", URL))["rolling"] is True

    def test_each_user_gets_their_own_season(self, alice: User, bob: User) -> None:
        race(alice, 6, title="Alice's race")
        race(bob, 12, title="Bob's race")

        mine = body(signed_in(alice).call("GET", URL))
        theirs = body(signed_in(bob).call("GET", URL))

        assert (len(mine["weeks"]), mine["main_race"]["title"]) == (7, "Alice's race")
        assert (len(theirs["weeks"]), theirs["main_race"]["title"]) == (13, "Bob's race")

    def test_the_illness_of_another_user_is_not_in_the_answer(self, alice: User, bob: User) -> None:
        UnavailablePeriod.objects.create(
            owner=bob,
            kind="illness",
            start_date=MONDAY + timedelta(days=1),
            end_date=MONDAY + timedelta(days=3),
        )

        assert body(signed_in(alice).call("GET", URL))["absences"] == []
        theirs = body(signed_in(bob).call("GET", URL))["absences"]
        assert [a["kind"] for a in theirs] == ["illness"]
