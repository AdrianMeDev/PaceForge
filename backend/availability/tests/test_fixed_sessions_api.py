import json
from http import HTTPStatus
from typing import Any
from uuid import uuid4

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from accounts.models import User
from accounts.tests.conftest import AuthApi
from availability.models import FixedSession
from availability.serializers import (
    FIXED_MINUTES_RANGE,
    FIXED_SLOT_CHOICE,
    FIXED_SPORT_CHOICE,
    FIXED_WEEKDAY_CHOICE,
    MAX_FIXED_SESSIONS,
    TOO_MANY_FIXED_SESSIONS,
)

from .conftest import make_user, signed_in

pytestmark = pytest.mark.django_db

URL = "/api/availability/fixed-sessions/"
FIELDS = {"id", "weekday", "sport", "minutes", "slot"}
TUESDAY_RUN = {"weekday": 1, "sport": "running", "minutes": 60}


@pytest.fixture
def alice() -> User:
    return make_user("alice@example.com")


@pytest.fixture
def bob() -> User:
    return make_user("bob@example.com")


def body(response: Any) -> Any:
    return json.loads(response.content)


def detail(pk: Any) -> str:
    return f"{URL}{pk}/"


def stored(owner: User, **fields: Any) -> FixedSession:
    return FixedSession.objects.create(owner=owner, **(TUESDAY_RUN | fields))


def create(api: AuthApi, data: Any) -> Any:
    return api.call("POST", URL, data)


def listing(api: AuthApi) -> list[dict[str, Any]]:
    response = api.call("GET", URL)
    assert response.status_code == HTTPStatus.OK
    return list(body(response))


class TestAccess:
    @pytest.mark.parametrize(
        ("method", "url"),
        [
            ("GET", URL),
            ("POST", URL),
            ("GET", detail(uuid4())),
            ("PATCH", detail(uuid4())),
            ("DELETE", detail(uuid4())),
        ],
    )
    def test_anonymous_visitors_are_refused(self, method: str, url: str) -> None:
        response = AuthApi().call(method, url, TUESDAY_RUN)

        assert response.status_code == HTTPStatus.FORBIDDEN
        assert not FixedSession.objects.exists()

    @pytest.mark.parametrize("method", ["POST", "PATCH", "DELETE"])
    def test_a_request_without_the_csrf_token_is_refused(self, alice: User, method: str) -> None:
        mine = stored(alice)
        api = signed_in(alice)
        url = URL if method == "POST" else detail(mine.pk)

        response = api.client.generic(
            method, url, data=json.dumps(TUESDAY_RUN), content_type="application/json"
        )

        assert response.status_code == HTTPStatus.FORBIDDEN
        assert FixedSession.objects.get().minutes == 60

    def test_put_is_not_allowed(self, alice: User) -> None:
        mine = stored(alice)

        response = signed_in(alice).call("PUT", detail(mine.pk), TUESDAY_RUN)

        assert response.status_code == HTTPStatus.METHOD_NOT_ALLOWED


class TestCreatingAndReading:
    def test_an_entry_is_created_and_read_back(self, alice: User) -> None:
        api = signed_in(alice)

        response = create(api, TUESDAY_RUN | {"slot": "evening"})

        assert response.status_code == HTTPStatus.CREATED
        created = body(response)
        assert set(created) == FIELDS
        assert created | {"id": None} == {
            "id": None,
            "weekday": 1,
            "sport": "running",
            "minutes": 60,
            "slot": "evening",
        }
        assert FixedSession.objects.get().owner == alice
        assert api.call("GET", detail(created["id"])).status_code == HTTPStatus.OK
        assert listing(api) == [created]

    def test_no_part_of_the_day_is_null(self, alice: User) -> None:
        created = body(create(signed_in(alice), TUESDAY_RUN))

        assert created["slot"] is None
        assert FixedSession.objects.get().slot == ""

    def test_an_explicit_null_means_no_part_of_the_day(self, alice: User) -> None:
        created = body(create(signed_in(alice), TUESDAY_RUN | {"slot": None}))

        assert created["slot"] is None

    def test_the_client_cannot_set_what_the_server_decides(self, alice: User, bob: User) -> None:
        response = create(
            signed_in(alice),
            TUESDAY_RUN | {"owner": str(bob.pk), "id": str(uuid4()), "owner_id": 1},
        )

        assert response.status_code == HTTPStatus.CREATED
        entry = FixedSession.objects.get()
        assert entry.owner == alice
        assert body(response)["id"] == str(entry.pk)

    def test_the_list_is_ordered_by_weekday_then_part_of_the_day(self, alice: User) -> None:
        late = stored(alice, weekday=4, slot="evening")
        early = stored(alice, weekday=4, slot="morning")
        none = stored(alice, weekday=4)
        monday = stored(alice, weekday=0, slot="evening")

        assert [entry["id"] for entry in listing(signed_in(alice))] == [
            str(monday.pk),
            str(none.pk),
            str(early.pk),
            str(late.pk),
        ]

    def test_the_list_is_a_plain_array_without_paging(self, alice: User) -> None:
        assert body(signed_in(alice).call("GET", URL)) == []

    def test_the_list_does_not_ask_the_database_once_per_entry(self, alice: User) -> None:
        api = signed_in(alice)
        for day in range(3):
            stored(alice, weekday=day)
        with CaptureQueriesContext(connection) as few:
            listing(api)
        for day in range(3, 7):
            stored(alice, weekday=day)

        with CaptureQueriesContext(connection) as many:
            listing(api)

        assert len(many) == len(few)

    def test_the_list_shows_only_the_own_entries(self, alice: User, bob: User) -> None:
        mine = stored(alice)
        stored(bob, weekday=3)

        assert [entry["id"] for entry in listing(signed_in(alice))] == [str(mine.pk)]


class TestRefusals:
    @pytest.mark.parametrize("weekday", [-1, 7, "1", 1.5, True, None, [1]])
    def test_an_unusable_weekday_is_refused(self, alice: User, weekday: Any) -> None:
        response = create(signed_in(alice), TUESDAY_RUN | {"weekday": weekday})

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert body(response) == {"weekday": [FIXED_WEEKDAY_CHOICE]}
        assert not FixedSession.objects.exists()

    @pytest.mark.parametrize("sport", ["", "golf", "Running", 5, True, ["running"], None])
    def test_an_unknown_sport_is_refused(self, alice: User, sport: Any) -> None:
        response = create(signed_in(alice), TUESDAY_RUN | {"sport": sport})

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert body(response) == {"sport": [FIXED_SPORT_CHOICE]}

    @pytest.mark.parametrize("minutes", [0, 4, 601, "60", 60.5, True, None, [60]])
    def test_unusable_minutes_are_refused(self, alice: User, minutes: Any) -> None:
        response = create(signed_in(alice), TUESDAY_RUN | {"minutes": minutes})

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert body(response) == {"minutes": [FIXED_MINUTES_RANGE]}

    @pytest.mark.parametrize("slot", ["", "night", "Morning", 1, True, ["morning"]])
    def test_an_unknown_slot_is_refused(self, alice: User, slot: Any) -> None:
        response = create(signed_in(alice), TUESDAY_RUN | {"slot": slot})

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert body(response) == {"slot": [FIXED_SLOT_CHOICE]}

    @pytest.mark.parametrize("missing", ["weekday", "sport", "minutes"])
    def test_a_missing_field_is_refused(self, alice: User, missing: str) -> None:
        data = {key: value for key, value in TUESDAY_RUN.items() if key != missing}

        response = create(signed_in(alice), data)

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert set(body(response)) == {missing}

    @pytest.mark.parametrize("data", [[], "x", 5, None])
    def test_a_body_that_is_no_object_is_refused(self, alice: User, data: Any) -> None:
        response = create(signed_in(alice), data)

        assert response.status_code == HTTPStatus.BAD_REQUEST

    def test_every_problem_is_named_at_once(self, alice: User) -> None:
        response = create(
            signed_in(alice), {"weekday": 9, "sport": "golf", "minutes": 1, "slot": "night"}
        )

        assert set(body(response)) == {"weekday", "sport", "minutes", "slot"}

    def test_the_messages_say_what_is_allowed(self) -> None:
        assert FIXED_WEEKDAY_CHOICE == "Choose a weekday from 0 (Monday) to 6 (Sunday)."
        assert FIXED_SPORT_CHOICE == "Choose one of: running, cycling, swimming, strength."
        assert FIXED_MINUTES_RANGE == "Enter a whole number of minutes between 5 and 600."
        assert FIXED_SLOT_CHOICE == (
            "Choose one of: morning, afternoon, evening, or null for no part of the day."
        )


class TestTheLimit:
    def test_the_limit_is_fourteen(self) -> None:
        assert MAX_FIXED_SESSIONS == 14

    def test_the_last_one_is_allowed_and_the_next_is_not(self, alice: User) -> None:
        FixedSession.objects.bulk_create(
            [FixedSession(owner=alice, **TUESDAY_RUN) for _ in range(MAX_FIXED_SESSIONS - 1)]
        )
        api = signed_in(alice)

        assert create(api, TUESDAY_RUN).status_code == HTTPStatus.CREATED
        response = create(api, TUESDAY_RUN)

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert body(response) == {"non_field_errors": [TOO_MANY_FIXED_SESSIONS]}
        assert FixedSession.objects.count() == MAX_FIXED_SESSIONS

    def test_other_users_entries_do_not_count(self, alice: User, bob: User) -> None:
        FixedSession.objects.bulk_create(
            [FixedSession(owner=bob, **TUESDAY_RUN) for _ in range(MAX_FIXED_SESSIONS)]
        )

        assert create(signed_in(alice), TUESDAY_RUN).status_code == HTTPStatus.CREATED

    def test_deleting_one_makes_room(self, alice: User) -> None:
        entries = FixedSession.objects.bulk_create(
            [FixedSession(owner=alice, **TUESDAY_RUN) for _ in range(MAX_FIXED_SESSIONS)]
        )
        api = signed_in(alice)
        api.call("DELETE", detail(entries[0].pk))

        assert create(api, TUESDAY_RUN).status_code == HTTPStatus.CREATED

    def test_changing_an_entry_is_not_stopped_by_a_full_list(self, alice: User) -> None:
        entries = FixedSession.objects.bulk_create(
            [FixedSession(owner=alice, **TUESDAY_RUN) for _ in range(MAX_FIXED_SESSIONS)]
        )

        response = signed_in(alice).call("PATCH", detail(entries[0].pk), {"minutes": 90})

        assert response.status_code == HTTPStatus.OK


class TestChanging:
    def test_one_field_changes_and_the_rest_stays(self, alice: User) -> None:
        mine = stored(alice, slot="evening")

        response = signed_in(alice).call("PATCH", detail(mine.pk), {"minutes": 90})

        assert response.status_code == HTTPStatus.OK
        mine.refresh_from_db()
        assert (mine.weekday, mine.sport, mine.minutes, mine.slot) == (1, "running", 90, "evening")

    def test_the_part_of_the_day_can_be_removed(self, alice: User) -> None:
        mine = stored(alice, slot="evening")

        response = signed_in(alice).call("PATCH", detail(mine.pk), {"slot": None})

        assert body(response)["slot"] is None
        mine.refresh_from_db()
        assert mine.slot == ""

    def test_a_refused_change_leaves_the_entry_as_it_was(self, alice: User) -> None:
        mine = stored(alice)

        response = signed_in(alice).call("PATCH", detail(mine.pk), {"minutes": 1000})

        assert response.status_code == HTTPStatus.BAD_REQUEST
        mine.refresh_from_db()
        assert mine.minutes == 60

    def test_the_owner_and_the_id_cannot_be_changed(self, alice: User, bob: User) -> None:
        mine = stored(alice)
        other = uuid4()

        response = signed_in(alice).call(
            "PATCH", detail(mine.pk), {"owner": str(bob.pk), "id": str(other), "minutes": 45}
        )

        assert response.status_code == HTTPStatus.OK
        mine.refresh_from_db()
        assert (mine.owner, mine.pk, mine.minutes) == (alice, mine.pk, 45)
        assert mine.pk != other


class TestDeleting:
    def test_an_entry_is_deleted(self, alice: User) -> None:
        mine = stored(alice)

        response = signed_in(alice).call("DELETE", detail(mine.pk))

        assert response.status_code == HTTPStatus.NO_CONTENT
        assert not FixedSession.objects.exists()


class TestOtherUsersAndIds:
    @pytest.mark.parametrize("method", ["GET", "PATCH", "DELETE"])
    def test_another_users_entry_does_not_exist(self, alice: User, bob: User, method: str) -> None:
        theirs = stored(bob)

        response = signed_in(alice).call(method, detail(theirs.pk), {"minutes": 45})

        assert response.status_code == HTTPStatus.NOT_FOUND
        theirs.refresh_from_db()
        assert theirs.minutes == 60

    @pytest.mark.parametrize("pk", ["1", "abc", "x" * 40])
    def test_an_id_that_is_no_uuid_is_not_found(self, alice: User, pk: str) -> None:
        assert signed_in(alice).call("GET", detail(pk)).status_code == HTTPStatus.NOT_FOUND

    def test_an_unknown_uuid_is_not_found(self, alice: User) -> None:
        assert signed_in(alice).call("GET", detail(uuid4())).status_code == HTTPStatus.NOT_FOUND
