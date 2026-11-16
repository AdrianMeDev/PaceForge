import json
from datetime import UTC, date, datetime
from http import HTTPStatus
from typing import Any
from uuid import UUID, uuid4

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from accounts.models import User
from accounts.tests.conftest import AuthApi
from athletes import best_times
from athletes.models import AthleteProfile, BestTime, ThresholdValue
from goals import services
from goals.models import Goal
from goals.serializers import MAIN_TAKEN, MAX_GOALS, PAST_RACE, TOO_MANY

from .conftest import make_user, signed_in

# A fixed id for the tests that are parametrized: the id is part of the name of a test, and
# every worker of a parallel run has to collect the same names.
UNKNOWN_ID = UUID("0195f3a0-0000-7000-8000-000000000001")

pytestmark = pytest.mark.django_db

URL = "/api/goals/"
NOW = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)
TODAY = date(2026, 11, 13)
FUTURE = "2027-09-26"
FIELDS = {
    "id", "kind", "title", "notes", "priority", "status", "target_date", "discipline",
    "distance_m", "target_time_seconds", "metric", "target_value", "days_to_go",
    "assessment", "created_at", "updated_at",
}  # fmt: skip


@pytest.fixture(autouse=True)
def _fixed_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(services, "_utc_now", lambda: NOW)
    monkeypatch.setattr(best_times, "_today", lambda: TODAY)


@pytest.fixture
def alice() -> User:
    return make_user("alice@example.com")


@pytest.fixture
def bob() -> User:
    return make_user("bob@example.com")


def body(response: Any) -> Any:
    return json.loads(response.content)


def race(**fields: Any) -> dict[str, Any]:
    return {
        "kind": "race",
        "title": "Berlin Marathon",
        "target_date": FUTURE,
        "discipline": "running",
        **fields,
    }


def threshold(**fields: Any) -> dict[str, Any]:
    return {
        "kind": "threshold",
        "title": "Raise my FTP",
        "metric": "ftp",
        "target_value": 280,
        **fields,
    }


def general(**fields: Any) -> dict[str, Any]:
    return {"kind": "general", "title": "Build endurance", **fields}


def create(api: AuthApi, data: dict[str, Any]) -> Any:
    return api.call("POST", URL, data)


def detail(goal_id: Any) -> str:
    return f"{URL}{goal_id}/"


def stored(owner: User, **fields: Any) -> Goal:
    return Goal.objects.create(owner=owner, **(race() | fields))


class TestWhoMayCome:
    @pytest.mark.parametrize(
        ("method", "url"),
        [
            ("GET", URL),
            ("POST", URL),
            ("GET", detail(UNKNOWN_ID)),
            ("PATCH", detail(UNKNOWN_ID)),
            ("DELETE", detail(UNKNOWN_ID)),
        ],
    )
    def test_anonymous_visitors_are_refused(self, method: str, url: str) -> None:
        assert AuthApi().call(method, url, race()).status_code == HTTPStatus.FORBIDDEN
        assert not Goal.objects.exists()

    @pytest.mark.parametrize("method", ["POST", "PATCH", "DELETE"])
    def test_a_request_without_the_csrf_token_is_refused(self, alice: User, method: str) -> None:
        goal = stored(alice)
        api = signed_in(alice)

        response = api.client.generic(
            method,
            URL if method == "POST" else detail(goal.pk),
            data=json.dumps(race(title="Changed")),
            content_type="application/json",
        )

        assert response.status_code == HTTPStatus.FORBIDDEN
        assert Goal.objects.get().title == "Berlin Marathon"


class TestCreatingAndReading:
    def test_a_race_is_created_and_read_back(self, alice: User) -> None:
        api = signed_in(alice)

        response = create(
            api, race(distance_m=42195, target_time_seconds=13500, notes="Flat course")
        )

        assert response.status_code == HTTPStatus.CREATED
        created = body(response)
        assert set(created) == FIELDS
        assert (created["kind"], created["title"], created["notes"]) == (
            "race",
            "Berlin Marathon",
            "Flat course",
        )
        assert (created["priority"], created["status"]) == ("secondary", "active")
        assert (created["discipline"], created["distance_m"], created["target_time_seconds"]) == (
            "running",
            42195,
            13500,
        )
        assert (created["metric"], created["target_value"]) == (None, None)
        assert created["target_date"] == FUTURE
        assert body(api.call("GET", URL)) == [created]
        assert body(api.call("GET", detail(created["id"]))) == created

    def test_a_threshold_goal_is_created(self, alice: User) -> None:
        created = body(create(signed_in(alice), threshold(target_date=FUTURE)))

        assert (created["metric"], created["target_value"]) == ("ftp", 280)
        assert (created["discipline"], created["distance_m"], created["target_time_seconds"]) == (
            None,
            None,
            None,
        )

    def test_a_general_goal_needs_only_a_title(self, alice: User) -> None:
        response = create(signed_in(alice), general())

        assert response.status_code == HTTPStatus.CREATED
        created = body(response)
        assert created["target_date"] is None and created["days_to_go"] is None

    def test_titles_are_trimmed_and_text_is_kept_as_text(self, alice: User) -> None:
        created = body(
            create(signed_in(alice), general(title="  <script>x</script>  ", notes="a<b>"))
        )

        assert created["title"] == "<script>x</script>"
        assert created["notes"] == "a<b>"

    def test_a_main_goal_can_be_created(self, alice: User) -> None:
        assert body(create(signed_in(alice), race(priority="main")))["priority"] == "main"

    def test_the_answers_have_no_owner_and_no_other_users_data(
        self, alice: User, bob: User
    ) -> None:
        stored(bob, title="Bob's secret")
        api = signed_in(alice)
        create(api, race())

        text = api.call("GET", URL).content.decode()

        assert str(alice.pk) not in text and str(bob.pk) not in text
        assert '"owner"' not in text and "secret" not in text

    def test_an_owner_or_id_in_the_body_is_ignored(self, alice: User, bob: User) -> None:
        wanted = uuid4()

        created = body(
            create(
                signed_in(alice),
                race(owner=str(bob.pk), id=str(wanted), created_at="2000-01-01T00:00:00Z"),
            )
        )

        goal = Goal.objects.get()
        assert goal.owner == alice
        assert created["id"] != str(wanted)
        assert not created["created_at"].startswith("2000")


class TestRefusals:
    @pytest.mark.parametrize(
        ("data", "field"),
        [
            ({"title": "x"}, "kind"),
            ({**race(), "kind": "dream"}, "kind"),
            ({**race(), "kind": None}, "kind"),
            (race(title=""), "title"),
            (race(title="   "), "title"),
            (race(title="x" * 101), "title"),
            (race(title=5), "title"),
            (race(title=["a"]), "title"),
            (race(notes=5), "notes"),
            (race(notes="x" * 1001), "notes"),
            (race(priority="urgent"), "priority"),
            (race(status="paused"), "status"),
            ({k: v for k, v in race().items() if k != "target_date"}, "target_date"),
            (race(target_date=None), "target_date"),
            (race(target_date="26.09.2027"), "target_date"),
            (race(target_date="2027-13-45"), "target_date"),
            ({k: v for k, v in race().items() if k != "discipline"}, "discipline"),
            (race(discipline="rowing"), "discipline"),
            (race(distance_m=0), "distance_m"),
            (race(distance_m=-5), "distance_m"),
            (race(distance_m=1_000_001), "distance_m"),
            (race(distance_m="42195"), "distance_m"),
            (race(distance_m=True), "distance_m"),
            (race(target_time_seconds=59), "target_time_seconds"),
            (race(target_time_seconds=360_001), "target_time_seconds"),
            (race(target_time_seconds="13500"), "target_time_seconds"),
            (race(target_time_seconds=13500.5), "target_time_seconds"),
            (race(target_time_seconds=True), "target_time_seconds"),
            (race(metric="ftp"), "metric"),
            (race(target_value=250), "target_value"),
            ({k: v for k, v in threshold().items() if k != "metric"}, "metric"),
            (threshold(metric="lthr"), "metric"),
            ({k: v for k, v in threshold().items() if k != "target_value"}, "target_value"),
            (threshold(target_value=29), "target_value"),
            (threshold(target_value=2001), "target_value"),
            (threshold(metric="threshold_pace", target_value=100), "target_value"),
            (threshold(target_value="280"), "target_value"),
            (threshold(discipline="running"), "discipline"),
            (threshold(distance_m=5000), "distance_m"),
            (general(discipline="running"), "discipline"),
            (general(metric="ftp"), "metric"),
            (general(target_time_seconds=3600), "target_time_seconds"),
        ],
    )
    def test_an_unusable_goal_is_refused_with_a_message_and_stores_nothing(
        self, alice: User, data: dict[str, Any], field: str
    ) -> None:
        response = create(signed_in(alice), data)

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert field in body(response), body(response)
        assert not Goal.objects.exists()

    @pytest.mark.parametrize("payload", [[1], "goal", 5, None, []])
    def test_a_body_of_the_wrong_type_is_a_400_and_never_a_500(
        self, alice: User, payload: Any
    ) -> None:
        api = signed_in(alice)

        assert create(api, payload).status_code == HTTPStatus.BAD_REQUEST
        assert not Goal.objects.exists()

    def test_the_message_names_the_range(self, alice: User) -> None:
        response = create(signed_in(alice), threshold(target_value=5000))

        assert body(response) == {"target_value": ["Enter a value between 30 and 2000 W."]}

    def test_a_body_that_is_no_json_is_a_400(self, alice: User) -> None:
        api = signed_in(alice)

        response = api.client.generic(
            "POST", URL, data=b"{not json", content_type="application/json",
            headers={"X-CSRFToken": api._csrf_token()},
        )  # fmt: skip

        assert response.status_code == HTTPStatus.BAD_REQUEST


class TestTheDate:
    def test_an_active_race_may_be_today_or_later_but_not_earlier(self, alice: User) -> None:
        api = signed_in(alice)

        assert (
            create(api, race(target_date="2026-11-12", title="a")).status_code
            == HTTPStatus.BAD_REQUEST
        )
        assert (
            create(api, race(target_date="2026-11-13", title="b")).status_code == HTTPStatus.CREATED
        )
        assert (
            create(api, race(target_date="2026-11-14", title="c")).status_code == HTTPStatus.CREATED
        )

    def test_the_message_says_what_to_do(self, alice: User) -> None:
        response = create(signed_in(alice), race(target_date="2020-01-01"))

        assert body(response) == {"target_date": [PAST_RACE]}

    @pytest.mark.parametrize("status", ["achieved", "dropped"])
    def test_a_finished_race_may_lie_in_the_past(self, alice: User, status: str) -> None:
        response = create(signed_in(alice), race(target_date="2020-01-01", status=status))

        assert response.status_code == HTTPStatus.CREATED

    @pytest.mark.parametrize("make", [threshold, general])
    def test_other_kinds_may_have_any_date(self, alice: User, make: Any) -> None:
        assert (
            create(signed_in(alice), make(target_date="2020-01-01")).status_code
            == HTTPStatus.CREATED
        )

    def test_today_follows_the_time_zone_of_the_profile(self, alice: User) -> None:
        """At 12:00 UTC it is the 14th in Auckland (UTC+13) and 02:00 on the 13th in Honolulu
        (UTC-10)."""
        api = signed_in(alice)
        AthleteProfile.objects.create(owner=alice, timezone="Pacific/Auckland")  # UTC+13: the 14th

        assert (
            create(api, race(target_date="2026-11-13", title="a")).status_code
            == HTTPStatus.BAD_REQUEST
        )
        assert (
            create(api, race(target_date="2026-11-14", title="b")).status_code == HTTPStatus.CREATED
        )

        AthleteProfile.objects.filter(owner=alice).update(
            timezone="Pacific/Honolulu"
        )  # UTC-10: the 13th, 02:00
        assert (
            create(api, race(target_date="2026-11-12", title="c")).status_code
            == HTTPStatus.BAD_REQUEST
        )
        assert (
            create(api, race(target_date="2026-11-13", title="d")).status_code == HTTPStatus.CREATED
        )

    def test_without_a_time_zone_it_is_utc(
        self, alice: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(services, "_utc_now", lambda: NOW.replace(hour=23, minute=30))
        api = signed_in(alice)

        assert create(api, race(target_date="2026-11-13")).status_code == HTTPStatus.CREATED
        assert (
            create(api, race(target_date="2026-11-12", title="b")).status_code
            == HTTPStatus.BAD_REQUEST
        )

    def test_a_time_zone_the_server_cannot_find_counts_as_utc(self, alice: User) -> None:
        AthleteProfile.objects.create(owner=alice, timezone="Mars/Base")  # cannot be saved normally

        assert services.today_of(alice) == TODAY

    @pytest.mark.parametrize(
        ("target", "days"),
        [("2026-11-13", 0), ("2026-11-25", 12), ("2026-11-10", -3), ("2027-11-13", 365)],
    )
    def test_days_to_go_counts_calendar_days(self, alice: User, target: str, days: int) -> None:
        stored(alice, target_date=date.fromisoformat(target), status="achieved")

        assert body(signed_in(alice).call("GET", URL))[0]["days_to_go"] == days

    def test_days_to_go_uses_the_time_zone_too(self, alice: User) -> None:
        AthleteProfile.objects.create(owner=alice, timezone="Pacific/Auckland")
        stored(alice, target_date=date(2026, 11, 14))

        assert body(signed_in(alice).call("GET", URL))[0]["days_to_go"] == 0

    def test_the_time_zone_is_looked_up_once_per_request(self, alice: User) -> None:
        for n in range(10):
            stored(alice, title=f"Race {n}")
        api = signed_in(alice)
        api.call("GET", URL)  # warm up

        with CaptureQueriesContext(connection) as queries:
            api.call("GET", URL)

        profile_queries = [q for q in queries if "athletes_athleteprofile" in q["sql"]]
        assert len(profile_queries) == 1
        assert len(queries) <= 6


ASSESSMENT = {
    "rating", "reason", "current", "needed", "suggested", "weeks", "prep_short", "prep_weeks"
}  # fmt: skip


def run_form(user: User, seconds: int = 2481) -> None:
    """A 10 km best time that is worth about VDOT 50."""
    BestTime.objects.create(owner=user, distance="10k", seconds=seconds, date=date(2026, 10, 14))


class TestTheAssessment:
    def test_a_race_with_a_form_is_judged(self, alice: User) -> None:
        run_form(alice)
        stored(alice, distance_m=10_000, target_time_seconds=2600, target_date=date(2027, 1, 22))

        (listed,) = body(signed_in(alice).call("GET", URL))

        assessment = listed["assessment"]
        assert set(assessment) == ASSESSMENT
        assert (assessment["rating"], assessment["reason"]) == ("realistic", None)
        assert assessment["current"] == pytest.approx(50, abs=0.2)
        assert assessment["weeks"] == 10
        assert (assessment["prep_short"], assessment["prep_weeks"]) == (False, 6)

    def test_an_unreasonable_target_is_unrealistic_with_a_suggestion(self, alice: User) -> None:
        run_form(alice)
        stored(alice, distance_m=10_000, target_time_seconds=1800, target_date=date(2027, 1, 22))

        (listed,) = body(signed_in(alice).call("GET", URL))

        assert listed["assessment"]["rating"] == "unrealistic"
        assert listed["assessment"]["suggested"] > 1800

    def test_a_goal_that_cannot_be_judged_says_why(self, alice: User) -> None:
        stored(alice, distance_m=10_000, target_time_seconds=2600)  # no best time

        (listed,) = body(signed_in(alice).call("GET", URL))

        assert (listed["assessment"]["rating"], listed["assessment"]["reason"]) == (
            "unknown",
            "no_form",
        )

    def test_a_threshold_goal_is_judged_against_the_current_value(self, alice: User) -> None:
        ThresholdValue.objects.create(
            owner=alice, sport="ride", metric="ftp", value=240, source="manual", basis="t"
        )
        Goal.objects.create(
            owner=alice, **threshold(target_value=400, target_date=date(2027, 1, 22))
        )

        (listed,) = body(signed_in(alice).call("GET", URL))

        assert listed["assessment"]["rating"] == "unrealistic"
        assert listed["assessment"]["suggested"] == 252

    def test_a_general_goal_has_none(self, alice: User) -> None:
        Goal.objects.create(owner=alice, **general())

        assert body(signed_in(alice).call("GET", URL))[0]["assessment"] is None

    @pytest.mark.parametrize("status", ["achieved", "dropped"])
    def test_a_goal_that_is_not_active_has_none(self, alice: User, status: str) -> None:
        run_form(alice)
        stored(alice, status=status, target_date=date(2026, 12, 1))

        assert body(signed_in(alice).call("GET", URL))[0]["assessment"] is None

    def test_one_goal_has_it_when_it_is_read_created_and_changed(self, alice: User) -> None:
        run_form(alice)
        api = signed_in(alice)
        created = body(create(api, race(distance_m=10_000, target_time_seconds=2600)))
        goal_id = created["id"]

        read = body(api.call("GET", detail(goal_id)))
        changed = body(api.call("PATCH", detail(goal_id), {"target_time_seconds": 1800}))

        assert created["assessment"]["rating"] == "realistic"
        assert read["assessment"] == created["assessment"]
        assert changed["assessment"]["rating"] == "unrealistic"

    def test_writing_ignores_it(self, alice: User) -> None:
        run_form(alice)
        goal = stored(alice, distance_m=10_000, target_time_seconds=2600)

        changed = body(
            signed_in(alice).call("PATCH", detail(goal.pk), {"assessment": {"rating": "x"}})
        )

        assert changed["assessment"]["rating"] in ("realistic", "ambitious", "unrealistic")

    def test_the_form_of_another_user_does_not_count(self, alice: User, bob: User) -> None:
        run_form(bob)
        stored(alice, distance_m=10_000, target_time_seconds=2600)

        (listed,) = body(signed_in(alice).call("GET", URL))

        assert listed["assessment"]["reason"] == "no_form"

    def test_it_holds_nothing_of_the_athletes_text(self, alice: User) -> None:
        run_form(alice)
        stored(alice, title="SECRET-TITLE", notes="SECRET-NOTES", target_date=date(2027, 1, 22))

        (listed,) = body(signed_in(alice).call("GET", URL))

        assert "SECRET" not in str(listed["assessment"])

    def test_the_queries_of_the_list_do_not_grow_with_the_goals(self, alice: User) -> None:
        run_form(alice)
        api = signed_in(alice)
        stored(alice, distance_m=10_000, target_time_seconds=2600, target_date=date(2027, 1, 22))
        api.call("GET", URL)  # warm up
        with CaptureQueriesContext(connection) as few:
            api.call("GET", URL)
        for n in range(15):
            stored(
                alice,
                priority="preparation",
                title=f"Race {n}",
                distance_m=10_000,
                target_time_seconds=2600,
                target_date=date(2027, 1, 22),
            )

        with CaptureQueriesContext(connection) as lots:
            api.call("GET", URL)

        assert len(few) == len(lots)


class TestTheMainGoal:
    def test_a_second_active_main_goal_is_refused(self, alice: User) -> None:
        api = signed_in(alice)
        create(api, race(priority="main"))

        response = create(api, race(priority="main", title="Another"))

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert body(response) == {"priority": [MAIN_TAKEN]}
        assert Goal.objects.count() == 1

    def test_secondary_goals_are_not_limited(self, alice: User) -> None:
        api = signed_in(alice)
        create(api, race(priority="main"))

        for n in range(3):
            assert create(api, race(title=f"Secondary {n}")).status_code == HTTPStatus.CREATED

    def test_a_secondary_goal_cannot_become_the_main_goal_while_there_is_one(
        self, alice: User
    ) -> None:
        stored(alice, priority="main")
        other = stored(alice, title="Other")

        response = signed_in(alice).call("PATCH", detail(other.pk), {"priority": "main"})

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert body(response) == {"priority": [MAIN_TAKEN]}
        other.refresh_from_db()
        assert other.priority == "secondary"

    def test_the_old_goal_can_be_changed_first(self, alice: User) -> None:
        old = stored(alice, priority="main")
        new = stored(alice, title="New")
        api = signed_in(alice)

        assert (
            api.call("PATCH", detail(old.pk), {"status": "achieved"}).status_code == HTTPStatus.OK
        )
        assert api.call("PATCH", detail(new.pk), {"priority": "main"}).status_code == HTTPStatus.OK

    def test_a_finished_main_goal_cannot_be_reactivated_while_another_is_active(
        self, alice: User
    ) -> None:
        old = stored(alice, priority="main", status="achieved")
        stored(alice, title="New", priority="main")

        response = signed_in(alice).call("PATCH", detail(old.pk), {"status": "active"})

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert "priority" in body(response)

    def test_changing_other_fields_of_the_main_goal_is_fine(self, alice: User) -> None:
        main = stored(alice, priority="main")

        response = signed_in(alice).call("PATCH", detail(main.pk), {"title": "Renamed"})

        assert response.status_code == HTTPStatus.OK

    @pytest.mark.parametrize("status", ["achieved", "dropped"])
    def test_a_finished_main_goal_can_be_created_next_to_an_active_one(
        self, alice: User, status: str
    ) -> None:
        stored(alice, priority="main")

        response = create(signed_in(alice), race(priority="main", status=status, title="Old"))

        assert response.status_code == HTTPStatus.CREATED

    def test_the_active_main_goal_can_be_finished_while_another_main_goal_is_finished(
        self, alice: User
    ) -> None:
        stored(alice, priority="main", status="achieved")
        active = stored(alice, priority="main", title="Active")

        response = signed_in(alice).call("PATCH", detail(active.pk), {"status": "dropped"})

        assert response.status_code == HTTPStatus.OK

    def test_every_user_has_their_own_main_goal(self, alice: User, bob: User) -> None:
        create(signed_in(alice), race(priority="main"))

        assert create(signed_in(bob), race(priority="main")).status_code == HTTPStatus.CREATED

    def test_two_requests_that_pass_the_check_meet_at_the_database(
        self, alice: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from goals.serializers import GoalSerializer

        stored(alice, priority="main")
        monkeypatch.setattr(GoalSerializer, "_check_the_main_goal", lambda self, goal: None)

        response = create(signed_in(alice), race(priority="main", title="Racing"))

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert body(response) == {"priority": [MAIN_TAKEN]}
        assert Goal.objects.count() == 1


class TestThePreparationRace:
    def test_a_race_is_created_as_a_preparation_race(self, alice: User) -> None:
        response = create(signed_in(alice), race(priority="preparation"))

        assert response.status_code == HTTPStatus.CREATED
        assert body(response)["priority"] == "preparation"

    @pytest.mark.parametrize("data", [threshold(), general()])
    def test_another_kind_is_refused_at_the_priority(
        self, alice: User, data: dict[str, Any]
    ) -> None:
        response = create(signed_in(alice), data | {"priority": "preparation"})

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert body(response) == {"priority": ["Only a race can be a preparation race."]}
        assert not Goal.objects.exists()

    def test_a_race_can_be_changed_to_one_and_back(self, alice: User) -> None:
        mine = stored(alice)
        api = signed_in(alice)

        up = api.call("PATCH", detail(mine.pk), {"priority": "preparation"})
        back = api.call("PATCH", detail(mine.pk), {"priority": "secondary"})

        assert (up.status_code, body(up)["priority"]) == (HTTPStatus.OK, "preparation")
        assert (back.status_code, body(back)["priority"]) == (HTTPStatus.OK, "secondary")

    def test_a_goal_that_is_not_a_race_cannot_be_changed_to_one(self, alice: User) -> None:
        mine = Goal.objects.create(owner=alice, **general())

        response = signed_in(alice).call("PATCH", detail(mine.pk), {"priority": "preparation"})

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert set(body(response)) == {"priority"}
        mine.refresh_from_db()
        assert mine.priority == "secondary"

    def test_it_does_not_count_as_the_main_goal(self, alice: User) -> None:
        api = signed_in(alice)
        create(api, race(priority="main"))

        for n in range(3):
            response = create(api, race(priority="preparation", title=f"Tune-up {n}"))
            assert response.status_code == HTTPStatus.CREATED

    def test_a_preparation_race_can_become_the_main_goal(self, alice: User) -> None:
        mine = stored(alice, priority="preparation")

        response = signed_in(alice).call("PATCH", detail(mine.pk), {"priority": "main"})

        assert response.status_code == HTTPStatus.OK

    def test_the_main_goal_rule_still_holds_against_it(self, alice: User) -> None:
        stored(alice, priority="main")
        mine = stored(alice, priority="preparation", title="Tune-up")

        response = signed_in(alice).call("PATCH", detail(mine.pk), {"priority": "main"})

        assert body(response) == {"priority": [MAIN_TAKEN]}


class TestOtherDatabaseErrors:
    def test_an_integrity_error_that_is_not_the_main_goal_rule_is_not_disguised(
        self, alice: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from django.db import IntegrityError

        def explode(self: Goal, *args: Any, **kwargs: Any) -> None:
            raise IntegrityError("some other constraint")

        monkeypatch.setattr(Goal, "save", explode)

        with pytest.raises(IntegrityError, match="some other"):
            create(signed_in(alice), race())


class TestNull:
    @pytest.mark.parametrize(
        "name", ["discipline", "metric", "distance_m", "target_time_seconds", "target_value"]
    )
    def test_a_null_for_something_that_does_not_apply_is_fine(self, alice: User, name: str) -> None:
        response = create(signed_in(alice), general(**{name: None}))

        assert response.status_code == HTTPStatus.CREATED
        assert body(response)[name] is None
        assert Goal.objects.get().metric == ""  # stored as an empty text, never as NULL

    def test_patching_a_null_into_a_text_field_does_not_break_the_database(
        self, alice: User
    ) -> None:
        goal = Goal.objects.create(owner=alice, **general())

        response = signed_in(alice).call(
            "PATCH", detail(goal.pk), {"metric": None, "discipline": None}
        )

        assert response.status_code == HTTPStatus.OK
        goal.refresh_from_db()
        assert (goal.metric, goal.discipline) == ("", "")


class TestTheLimit:
    def fill(self, owner: User, count: int) -> None:
        Goal.objects.bulk_create(
            Goal(owner=owner, kind="general", title=f"Goal {n}") for n in range(count)
        )

    def test_the_limit_is_thirty(self) -> None:
        assert MAX_GOALS == 30
        assert "30" in TOO_MANY

    def test_the_last_goal_is_accepted_and_the_next_one_is_not(self, alice: User) -> None:
        self.fill(alice, MAX_GOALS - 1)
        api = signed_in(alice)

        assert create(api, general()).status_code == HTTPStatus.CREATED
        response = create(api, general(title="One too many"))

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert body(response) == {"non_field_errors": [TOO_MANY]}
        assert Goal.objects.count() == MAX_GOALS

    def test_deleting_one_makes_room(self, alice: User) -> None:
        self.fill(alice, MAX_GOALS)
        api = signed_in(alice)
        api.call("DELETE", detail(Goal.objects.first().pk))  # type: ignore[union-attr]

        assert create(api, general()).status_code == HTTPStatus.CREATED

    def test_goals_of_others_do_not_count(self, alice: User, bob: User) -> None:
        self.fill(bob, MAX_GOALS)

        assert create(signed_in(alice), general()).status_code == HTTPStatus.CREATED

    def test_changing_goals_is_possible_at_the_limit(self, alice: User) -> None:
        self.fill(alice, MAX_GOALS)
        goal = Goal.objects.first()
        assert goal is not None

        response = signed_in(alice).call("PATCH", detail(goal.pk), {"title": "Renamed"})

        assert response.status_code == HTTPStatus.OK


class TestChanging:
    def test_one_field_changes_and_the_others_stay(self, alice: User) -> None:
        goal = stored(alice, distance_m=42195, notes="keep")

        changed = body(signed_in(alice).call("PATCH", detail(goal.pk), {"title": "Renamed"}))

        assert changed["title"] == "Renamed"
        assert (changed["distance_m"], changed["notes"], changed["target_date"]) == (
            42195,
            "keep",
            FUTURE,
        )

    @pytest.mark.parametrize("status", ["achieved", "dropped", "active"])
    def test_the_status_can_be_changed(self, alice: User, status: str) -> None:
        goal = stored(alice, status="achieved" if status == "active" else "active")

        response = signed_in(alice).call("PATCH", detail(goal.pk), {"status": status})

        assert body(response)["status"] == status

    def test_an_optional_value_can_be_cleared(self, alice: User) -> None:
        goal = stored(alice, target_time_seconds=13500, distance_m=42195)

        changed = body(
            signed_in(alice).call(
                "PATCH", detail(goal.pk), {"target_time_seconds": None, "distance_m": None}
            )
        )

        assert (changed["target_time_seconds"], changed["distance_m"]) == (None, None)

    @pytest.mark.parametrize(
        ("changes", "field"),
        [
            ({"target_date": None}, "target_date"),
            ({"discipline": None}, "discipline"),
            ({"discipline": ""}, "discipline"),
            ({"kind": "general"}, "kind"),
            ({"kind": "threshold"}, "kind"),
            ({"metric": "ftp"}, "metric"),
            ({"title": ""}, "title"),
            ({"target_time_seconds": 10}, "target_time_seconds"),
            ({"distance_m": "far"}, "distance_m"),
        ],
    )
    def test_a_change_that_leaves_the_goal_unusable_is_refused_and_changes_nothing(
        self, alice: User, changes: dict[str, Any], field: str
    ) -> None:
        goal = stored(alice, target_time_seconds=13500)

        response = signed_in(alice).call("PATCH", detail(goal.pk), changes)

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert field in body(response)
        before = Goal.objects.get(pk=goal.pk)
        assert (before.title, before.target_date, before.discipline, before.kind) == (
            "Berlin Marathon", date.fromisoformat(FUTURE), "running", "race",
        )  # fmt: skip

    def test_the_kind_may_be_repeated_but_not_changed(self, alice: User) -> None:
        goal = stored(alice)
        api = signed_in(alice)

        assert (
            api.call("PATCH", detail(goal.pk), {"kind": "race", "title": "Same kind"}).status_code
            == HTTPStatus.OK
        )
        assert body(api.call("PATCH", detail(goal.pk), {"kind": "general"})) == {
            "kind": ["The kind of a goal cannot be changed."]
        }

    def test_a_threshold_goal_can_get_a_new_target(self, alice: User) -> None:
        goal = Goal.objects.create(owner=alice, **threshold())

        changed = body(signed_in(alice).call("PATCH", detail(goal.pk), {"target_value": 300}))

        assert changed["target_value"] == 300

    def test_a_past_race_cannot_be_reactivated_but_can_be_renamed(self, alice: User) -> None:
        goal = stored(alice, target_date=date(2026, 1, 1), status="achieved")
        api = signed_in(alice)

        assert api.call("PATCH", detail(goal.pk), {"title": "Renamed"}).status_code == HTTPStatus.OK
        again = api.call("PATCH", detail(goal.pk), {"status": "active"})
        assert again.status_code == HTTPStatus.BAD_REQUEST
        assert body(again) == {"target_date": [PAST_RACE]}

    def test_the_date_of_an_active_race_cannot_move_into_the_past(self, alice: User) -> None:
        goal = stored(alice)

        response = signed_in(alice).call("PATCH", detail(goal.pk), {"target_date": "2026-01-01"})

        assert response.status_code == HTTPStatus.BAD_REQUEST

    def test_an_active_race_that_became_past_can_still_be_changed_otherwise(
        self, alice: User
    ) -> None:
        goal = stored(alice, target_date=date(2026, 11, 1))  # created earlier, now past

        response = signed_in(alice).call("PATCH", detail(goal.pk), {"notes": "How did it go?"})

        assert response.status_code == HTTPStatus.OK

    def test_put_is_not_offered(self, alice: User) -> None:
        goal = stored(alice)

        assert (
            signed_in(alice).call("PUT", detail(goal.pk), race()).status_code
            == HTTPStatus.METHOD_NOT_ALLOWED
        )

    def test_server_fields_in_the_body_are_ignored(self, alice: User, bob: User) -> None:
        goal = stored(alice)

        changed = body(
            signed_in(alice).call(
                "PATCH", detail(goal.pk),
                {
                    "title": "T", "owner": str(bob.pk), "id": str(uuid4()),
                    "days_to_go": 99, "created_at": "2000-01-01T00:00:00Z",
                },
            )
        )  # fmt: skip

        assert changed["id"] == str(goal.pk) and changed["days_to_go"] != 99
        assert Goal.objects.get().owner == alice

    def test_the_time_of_the_last_change_moves(self, alice: User) -> None:
        goal = stored(alice)
        first = goal.updated_at

        changed = body(signed_in(alice).call("PATCH", detail(goal.pk), {"title": "Later"}))

        assert changed["updated_at"] > first.isoformat().replace("+00:00", "Z")[:-1]


class TestDeleting:
    def test_a_goal_is_deleted(self, alice: User) -> None:
        goal = stored(alice)
        api = signed_in(alice)

        assert api.call("DELETE", detail(goal.pk)).status_code == HTTPStatus.NO_CONTENT
        assert not Goal.objects.exists()
        assert api.call("GET", detail(goal.pk)).status_code == HTTPStatus.NOT_FOUND

    def test_deleting_a_main_goal_makes_room_for_the_next(self, alice: User) -> None:
        main = stored(alice, priority="main")
        api = signed_in(alice)
        api.call("DELETE", detail(main.pk))

        assert create(api, race(priority="main", title="New")).status_code == HTTPStatus.CREATED


class TestOrder:
    def test_active_before_achieved_before_dropped_main_first_then_by_date(
        self, alice: User
    ) -> None:
        def add(title: str, **fields: Any) -> None:
            Goal.objects.create(owner=alice, **(general(title=title) | fields))

        add("dropped", status="dropped")
        add("achieved", status="achieved", target_date=date(2026, 1, 1))
        add("secondary late", target_date=date(2027, 6, 1))
        add("secondary early", target_date=date(2027, 1, 1))
        add("secondary undated")
        add("main", priority="main", target_date=date(2028, 1, 1))

        titles = [goal["title"] for goal in body(signed_in(alice).call("GET", URL))]

        assert titles == [
            "main", "secondary early", "secondary late", "secondary undated", "achieved", "dropped"
        ]  # fmt: skip

    def test_preparation_races_come_after_the_secondary_goals_by_date(self, alice: User) -> None:
        def add(title: str, **fields: Any) -> None:
            Goal.objects.create(owner=alice, **(race(title=title, target_date=None) | fields))

        add("c late", priority="preparation", target_date=date(2027, 5, 1))
        add("c early", priority="preparation", target_date=date(2027, 3, 1))
        add("b", target_date=date(2028, 1, 1))
        add("a", priority="main", target_date=date(2028, 6, 1))
        add("c done", priority="preparation", status="achieved", target_date=date(2026, 1, 1))

        titles = [goal["title"] for goal in body(signed_in(alice).call("GET", URL))]

        assert titles == ["a", "b", "c early", "c late", "c done"]

    def test_goals_with_the_same_date_come_in_the_order_they_were_made(self, alice: User) -> None:
        for n in range(3):
            stored(alice, title=f"Race {n}")

        titles = [goal["title"] for goal in body(signed_in(alice).call("GET", URL))]

        assert titles == ["Race 0", "Race 1", "Race 2"]

    def test_the_list_is_a_plain_list_without_paging(self, alice: User) -> None:
        for n in range(25):
            Goal.objects.create(owner=alice, **general(title=f"Goal {n}"))

        listed = body(signed_in(alice).call("GET", URL))

        assert isinstance(listed, list) and len(listed) == 25

    def test_the_list_needs_no_query_per_goal(
        self, alice: User, django_assert_max_num_queries: Any
    ) -> None:
        for n in range(20):
            Goal.objects.create(owner=alice, **general(title=f"Goal {n}"))
        api = signed_in(alice)

        with django_assert_max_num_queries(6):
            api.call("GET", URL)


class TestIsolation:
    def test_each_user_lists_only_their_own_goals(self, alice: User, bob: User) -> None:
        mine, theirs = stored(alice, title="Mine"), stored(bob, title="Theirs")

        assert [g["id"] for g in body(signed_in(alice).call("GET", URL))] == [str(mine.pk)]
        assert [g["id"] for g in body(signed_in(bob).call("GET", URL))] == [str(theirs.pk)]

    def test_a_foreign_goal_answers_404_for_read_change_and_delete(
        self, alice: User, bob: User
    ) -> None:
        theirs = stored(bob)
        api = signed_in(alice)

        assert api.call("GET", detail(theirs.pk)).status_code == HTTPStatus.NOT_FOUND
        assert (
            api.call("PATCH", detail(theirs.pk), {"title": "Mine now"}).status_code
            == HTTPStatus.NOT_FOUND
        )
        assert api.call("DELETE", detail(theirs.pk)).status_code == HTTPStatus.NOT_FOUND
        theirs.refresh_from_db()
        assert theirs.title == "Berlin Marathon"

    def test_an_administrator_sees_only_their_own_goals(self, alice: User) -> None:
        boss = make_user("boss@example.com", staff=True)
        stored(alice)

        assert body(signed_in(boss).call("GET", URL)) == []

    @pytest.mark.parametrize("ident", ["not-a-uuid", "12345", str(UNKNOWN_ID)])
    def test_an_unknown_id_is_a_404(self, alice: User, ident: str) -> None:
        api = signed_in(alice)

        assert api.call("GET", detail(ident)).status_code == HTTPStatus.NOT_FOUND
        assert api.call("PATCH", detail(ident), {"title": "x"}).status_code == HTTPStatus.NOT_FOUND
        assert api.call("DELETE", detail(ident)).status_code == HTTPStatus.NOT_FOUND

    def test_a_goal_of_another_user_does_not_block_the_main_goal(
        self, alice: User, bob: User
    ) -> None:
        stored(bob, priority="main")

        assert create(signed_in(alice), race(priority="main")).status_code == HTTPStatus.CREATED

    def test_nothing_about_the_goals_is_logged(
        self, alice: User, caplog: pytest.LogCaptureFixture
    ) -> None:
        import logging

        caplog.set_level(logging.DEBUG)
        api = signed_in(alice)

        create(api, race(title="Secret ambition", notes="private notes"))
        api.call("GET", URL)

        assert "Secret ambition" not in caplog.text and "private notes" not in caplog.text
