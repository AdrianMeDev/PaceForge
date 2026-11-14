import json
from datetime import UTC, date, datetime, timedelta
from http import HTTPStatus
from typing import Any

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from accounts.models import User
from accounts.tests.conftest import AuthApi
from activities import services
from activities.models import Activity, ActivityFile
from athletes.models import AthleteProfile
from planning.context import build_context

from .conftest import make_user, signed_in
from .fit_builder import activity_file

pytestmark = pytest.mark.django_db

MANUAL = "/api/activities/manual/"
MARKER = "SECRETMARKER"
START = datetime(2026, 11, 12, 6, 30, tzinfo=UTC)

FORM: dict[str, Any] = {
    "sport": "strength",
    "date": "2026-11-12",
    "time": "06:30",
    "duration_minutes": 45,
}


@pytest.fixture
def alice() -> User:
    return make_user("alice@example.com")


@pytest.fixture
def bob() -> User:
    return make_user("bob@example.com")


def enter(user: User, **changes: Any) -> Any:
    form = {**FORM, **changes}
    form = {key: value for key, value in form.items() if value is not _OMIT}
    return signed_in(user).call("POST", MANUAL, form)


_OMIT = object()


def body(response: Any) -> Any:
    return json.loads(response.content)


class TestEntering:
    def test_a_session_is_stored_without_a_file(self, alice: User) -> None:
        response = enter(alice)

        assert response.status_code == HTTPStatus.CREATED
        stored = Activity.objects.get()
        assert (stored.owner, stored.source, stored.sport) == (alice, "manual", "strength")
        assert stored.start_time == START
        assert stored.timer_seconds == 2700
        assert (stored.source_hash, stored.best_efforts) == ("", {})
        assert (stored.rpe, stored.notes, stored.distance_m) == (None, "", None)
        assert ActivityFile.objects.count() == 0

    def test_the_answer_is_the_summary_of_the_activity(self, alice: User) -> None:
        data = body(enter(alice, rpe=7, notes="Legs were heavy", distance_km=5.5))

        assert data["source"] == "manual"
        assert data["id"] == str(Activity.objects.get().pk)
        assert (data["rpe"], data["notes"], data["distance_m"]) == (7, "Legs were heavy", 5500)
        assert (data["timer_seconds"], data["load"]) == (2700, 315)
        assert "source_hash" not in data

    def test_it_shows_in_the_list_of_the_user(self, alice: User) -> None:
        enter(alice)

        listed = signed_in(alice).call("GET", "/api/activities/").json()["results"]

        assert [item["source"] for item in listed] == ["manual"]

    def test_the_sport_may_be_any_of_the_sports_of_an_activity(self, alice: User) -> None:
        for number, sport in enumerate(Activity.Sport.values):
            assert enter(alice, sport=sport, time=f"0{number}:00").status_code == 201

    @pytest.mark.parametrize(
        ("zone", "date_text", "clock", "utc"),
        [
            ("UTC", "2026-11-12", "06:30", datetime(2026, 11, 12, 6, 30, tzinfo=UTC)),
            ("Europe/Berlin", "2026-11-12", "06:30", datetime(2026, 11, 12, 5, 30, tzinfo=UTC)),
            # Just after midnight local time is still the day before in UTC.
            ("Europe/Berlin", "2026-11-12", "00:30", datetime(2026, 11, 11, 23, 30, tzinfo=UTC)),
            # Summer time.
            ("Europe/Berlin", "2026-07-12", "08:00", datetime(2026, 7, 12, 6, 0, tzinfo=UTC)),
            ("America/New_York", "2026-11-12", "20:00", datetime(2026, 11, 13, 1, 0, tzinfo=UTC)),
        ],
    )
    def test_the_time_is_the_wall_clock_of_the_users_time_zone(
        self, alice: User, zone: str, date_text: str, clock: str, utc: datetime
    ) -> None:
        AthleteProfile.objects.create(owner=alice, timezone=zone)

        assert enter(alice, date=date_text, time=clock).status_code == 201

        assert Activity.objects.get().start_time == utc

    def test_without_a_profile_the_time_is_utc(self, alice: User) -> None:
        enter(alice, time="23:59")

        assert Activity.objects.get().start_time == datetime(2026, 11, 12, 23, 59, tzinfo=UTC)

    def test_it_counts_for_the_minutes_of_the_last_weeks(self, alice: User) -> None:
        enter(alice, sport="running", duration_minutes=60)

        context = build_context(alice, date(2026, 11, 16))

        assert context.recent_weeks == (60,)


class TestLimits:
    @pytest.mark.parametrize(
        "changes",
        [
            {"duration_minutes": 1},
            {"duration_minutes": 1440},
            {"distance_km": 0},
            {"distance_km": 1000},
            {"distance_km": None},
            {"rpe": 1},
            {"rpe": 10},
            {"rpe": None},
            {"notes": "x" * 500},
            {"notes": ""},
            {"notes": "Line one\nLine two"},
            {"date": "2000-01-01"},
            {"time": "00:00"},
            {"time": "23:59"},
        ],
    )
    def test_these_are_still_fine(self, alice: User, changes: dict[str, Any]) -> None:
        assert enter(alice, **changes).status_code == HTTPStatus.CREATED

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("sport", "yoga"),
            ("sport", ""),
            ("sport", 5),
            ("sport", None),
            ("sport", _OMIT),
            ("date", _OMIT),
            ("date", "2026-13-01"),
            ("date", "2026-02-30"),
            ("date", "12.11.2026"),
            ("date", 20261112),
            ("date", "1999-12-31"),
            ("date", "2099-01-01"),
            ("time", _OMIT),
            ("time", "25:00"),
            ("time", "6:30pm"),
            ("time", "06:30:15"),
            ("time", 630),
            ("duration_minutes", _OMIT),
            ("duration_minutes", 0),
            ("duration_minutes", 1441),
            ("duration_minutes", -5),
            ("duration_minutes", 1.5),
            ("duration_minutes", "60"),
            ("duration_minutes", True),
            ("duration_minutes", None),
            ("distance_km", -0.1),
            ("distance_km", 1000.1),
            ("distance_km", "5"),
            ("distance_km", True),
            ("rpe", 0),
            ("rpe", 11),
            ("rpe", 5.5),
            ("rpe", "7"),
            ("rpe", True),
            ("notes", "x" * 501),
            ("notes", 5),
            ("notes", "bell\x07"),
            ("notes", "null\x00byte"),
            ("notes", "reversed ‮text"),
            ("notes", "line separator"),
        ],
    )
    def test_everything_else_is_refused_and_nothing_is_stored(
        self, alice: User, field: str, value: Any
    ) -> None:
        response = enter(alice, **{field: value})

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert field in body(response)
        assert Activity.objects.count() == 0

    def test_a_number_that_is_no_number_is_refused_by_the_parser(self, alice: User) -> None:
        response = enter(alice, distance_km=float("nan"))

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert Activity.objects.count() == 0

    def test_a_session_in_the_future_is_refused(self, alice: User) -> None:
        tomorrow = (datetime.now(UTC) + timedelta(days=2)).date().isoformat()

        response = enter(alice, date=tomorrow, time="12:00")

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert body(response)["date"] == ["The session cannot start in the future."]

    def test_every_problem_is_reported_at_once(self, alice: User) -> None:
        response = enter(alice, sport="yoga", duration_minutes=0, rpe=11)

        assert set(body(response)) == {"sport", "duration_minutes", "rpe"}

    def test_nothing_of_the_input_is_repeated_in_an_error(self, alice: User) -> None:
        bad = {
            "sport": MARKER,
            "date": MARKER,
            "time": MARKER,
            "duration_minutes": MARKER,
            "distance_km": MARKER,
            "rpe": MARKER,
            "notes": MARKER + "\x00",
        }

        response = enter(alice, **bad)

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert MARKER not in response.content.decode()

    def test_unknown_fields_are_ignored_not_stored(self, alice: User) -> None:
        enter(alice, owner=999, source="fit_file", source_hash="a" * 64, load=1, id="x")

        stored = Activity.objects.get()
        assert (stored.owner, stored.source, stored.source_hash) == (alice, "manual", "")


class TestDuplicates:
    def test_the_same_session_twice_is_refused_with_the_existing_id(self, alice: User) -> None:
        first = enter(alice)

        second = enter(alice)

        assert second.status_code == HTTPStatus.CONFLICT
        assert body(second) == {
            "detail": "This activity has already been imported.",
            "existing_id": body(first)["id"],
        }
        assert Activity.objects.count() == 1

    def test_a_session_a_few_minutes_later_of_the_same_length_is_the_same_one(
        self, alice: User
    ) -> None:
        first = enter(alice)

        second = enter(alice, time="06:36")

        assert second.status_code == HTTPStatus.CONFLICT
        assert body(second)["existing_id"] == body(first)["id"]

    def test_a_session_of_another_length_at_a_near_time_is_another_one(self, alice: User) -> None:
        enter(alice)

        assert enter(alice, time="06:36", duration_minutes=90).status_code == HTTPStatus.CREATED

    def test_the_same_start_in_another_sport_is_another_session(self, alice: User) -> None:
        enter(alice)

        assert enter(alice, sport="running").status_code == HTTPStatus.CREATED

    def test_a_file_of_the_same_run_is_the_same_session(self, alice: User) -> None:
        services.import_activity(alice, activity_file())

        response = enter(alice, sport="running", duration_minutes=65)

        assert response.status_code == HTTPStatus.CONFLICT

    def test_another_user_does_not_matter_and_is_not_revealed(self, alice: User, bob: User) -> None:
        mine = body(enter(alice))

        theirs = enter(bob)

        assert theirs.status_code == HTTPStatus.CREATED
        assert body(theirs)["id"] != mine["id"]

    def test_an_insert_that_loses_a_race_is_reported_as_a_duplicate(
        self, alice: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        enter(alice)
        real = services.find_duplicate
        answers = iter([None])
        monkeypatch.setattr(
            services,
            "find_duplicate",
            lambda *args, **kwargs: next(answers, None) or real(*args, **kwargs),
        )

        response = enter(alice)

        assert response.status_code == HTTPStatus.CONFLICT
        assert Activity.objects.count() == 1

    def test_an_integrity_error_that_is_no_duplicate_is_not_hidden(
        self, alice: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A rating the database refuses although the form let it pass.
        monkeypatch.setattr(services, "find_duplicate", lambda *args, **kwargs: None)
        with pytest.raises(Exception, match="activities_rpe_in_range"):
            services.enter_activity(
                alice, sport="strength", start=START, duration_minutes=45, rpe=11
            )


class TestAccess:
    def test_anonymous_visitors_are_refused(self) -> None:
        assert AuthApi().call("POST", MANUAL, FORM).status_code == HTTPStatus.FORBIDDEN

    def test_a_post_without_the_csrf_token_is_refused(self, alice: User) -> None:
        api = signed_in(alice)

        response = api.client.generic(
            "POST", MANUAL, data=json.dumps(FORM), content_type="application/json"
        )

        assert response.status_code == HTTPStatus.FORBIDDEN
        assert Activity.objects.count() == 0

    @pytest.mark.parametrize("method", ["GET", "PUT", "PATCH", "DELETE"])
    def test_other_methods_are_not_allowed(self, alice: User, method: str) -> None:
        response = signed_in(alice).call(method, MANUAL)

        assert response.status_code == HTTPStatus.METHOD_NOT_ALLOWED

    def test_it_shares_the_limit_of_the_import(self, alice: User) -> None:
        api = signed_in(alice)

        statuses = [api.call("POST", MANUAL, FORM).status_code for _ in range(31)]

        assert statuses[-1] == HTTPStatus.TOO_MANY_REQUESTS
        assert statuses[:30].count(HTTPStatus.TOO_MANY_REQUESTS) == 0

    def test_an_import_counts_for_the_same_limit(self, alice: User) -> None:
        api = signed_in(alice)
        for _ in range(30):
            api.client.post(
                "/api/activities/import/",
                {"file": SimpleUploadedFile("x.fit", b"")},
                headers={"X-CSRFToken": api._csrf_token()},
            )

        assert api.call("POST", MANUAL, FORM).status_code == HTTPStatus.TOO_MANY_REQUESTS
