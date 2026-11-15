import json
from http import HTTPStatus
from typing import Any
from uuid import uuid4

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from accounts.models import User
from accounts.tests.conftest import AuthApi
from availability.models import Limitation
from availability.serializers import (
    BODY_PART_CHOICE,
    LIMITATION_SPORTS_CHOICE,
    LIMITATION_STATUS_CHOICE,
    MAX_LIMITATIONS,
    TOO_MANY_LIMITATIONS,
)

from .conftest import make_user, signed_in

pytestmark = pytest.mark.django_db

URL = "/api/availability/limitations/"
FIELDS = {"id", "body_part", "status", "sports"}


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


def stored(owner: User, **fields: Any) -> Limitation:
    return Limitation.objects.create(owner=owner, **({"body_part": "knee"} | fields))


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
        response = AuthApi().call(method, url, {"body_part": "knee"})

        assert response.status_code == HTTPStatus.FORBIDDEN
        assert not Limitation.objects.exists()

    @pytest.mark.parametrize("method", ["POST", "PATCH", "DELETE"])
    def test_a_request_without_the_csrf_token_is_refused(self, alice: User, method: str) -> None:
        mine = stored(alice)
        api = signed_in(alice)

        response = api.client.generic(
            method,
            URL if method == "POST" else detail(mine.pk),
            data=json.dumps({"body_part": "back"}),
            content_type="application/json",
        )

        assert response.status_code == HTTPStatus.FORBIDDEN
        assert Limitation.objects.get().body_part == "knee"

    def test_put_is_not_allowed(self, alice: User) -> None:
        mine = stored(alice)

        response = signed_in(alice).call("PUT", detail(mine.pk), {"body_part": "back"})

        assert response.status_code == HTTPStatus.METHOD_NOT_ALLOWED


class TestCreatingAndReading:
    def test_an_entry_is_created_and_read_back(self, alice: User) -> None:
        api = signed_in(alice)

        response = create(api, {"body_part": "achilles", "sports": ["running"]})

        assert response.status_code == HTTPStatus.CREATED
        created = body(response)
        assert set(created) == FIELDS
        assert created | {"id": None} == {
            "id": None,
            "body_part": "achilles",
            "status": "current",
            "sports": ["running"],
        }
        assert Limitation.objects.get().owner == alice
        assert api.call("GET", detail(created["id"])).status_code == HTTPStatus.OK
        assert listing(api) == [created]

    def test_the_defaults_are_current_and_no_particular_sport(self, alice: User) -> None:
        created = body(create(signed_in(alice), {"body_part": "back"}))

        assert (created["status"], created["sports"]) == ("current", [])

    def test_the_status_can_be_given_when_creating(self, alice: User) -> None:
        created = body(create(signed_in(alice), {"body_part": "back", "status": "healed"}))

        assert created["status"] == "healed"

    @pytest.mark.parametrize("part", ["foot", "ankle", "achilles", "calf", "shin", "knee"])
    def test_the_body_parts_of_the_list_are_accepted(self, alice: User, part: str) -> None:
        assert create(signed_in(alice), {"body_part": part}).status_code == HTTPStatus.CREATED

    def test_the_sports_are_kept_in_the_order_of_the_sports(self, alice: User) -> None:
        created = body(
            create(signed_in(alice), {"body_part": "knee", "sports": ["strength", "running"]})
        )

        assert created["sports"] == ["running", "strength"]

    def test_the_client_cannot_set_what_the_server_decides(self, alice: User, bob: User) -> None:
        response = create(
            signed_in(alice),
            {"body_part": "knee", "id": str(uuid4()), "owner": str(bob.pk), "note": "x"},
        )

        assert response.status_code == HTTPStatus.CREATED
        entry = Limitation.objects.get()
        assert entry.owner == alice
        assert str(entry.pk) == body(response)["id"]
        assert "note" not in body(response)

    def test_current_entries_come_first_then_healed_ones_the_newest_first(
        self, alice: User
    ) -> None:
        old_current = stored(alice, body_part="foot")
        healed = stored(alice, body_part="back", status="healed")
        new_current = stored(alice, body_part="hip")
        newest_healed = stored(alice, body_part="calf", status="healed")

        order = [entry["id"] for entry in listing(signed_in(alice))]

        assert order == [
            str(pk) for pk in (new_current.pk, old_current.pk, newest_healed.pk, healed.pk)
        ]

    def test_the_list_is_a_plain_array_without_paging(self, alice: User) -> None:
        assert body(signed_in(alice).call("GET", URL)) == []

    def test_the_list_does_not_ask_the_database_once_per_entry(self, alice: User) -> None:
        api = signed_in(alice)
        for part in ("foot", "knee", "hip"):
            stored(alice, body_part=part)
        with CaptureQueriesContext(connection) as few:
            listing(api)
        for part in ("back", "calf", "shin", "ankle", "thigh"):
            stored(alice, body_part=part)

        with CaptureQueriesContext(connection) as many:
            listing(api)

        assert len(many) == len(few)

    def test_the_list_shows_only_the_own_entries(self, alice: User, bob: User) -> None:
        mine = stored(alice, body_part="knee")
        stored(bob, body_part="back")

        assert [entry["id"] for entry in listing(signed_in(alice))] == [str(mine.pk)]


class TestRefusals:
    @pytest.mark.parametrize("part", ["", "elbow", "Knee", "KNEE", 5, True, ["knee"], None])
    def test_an_unknown_body_part_is_refused(self, alice: User, part: Any) -> None:
        response = create(signed_in(alice), {"body_part": part})

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert body(response) == {"body_part": [BODY_PART_CHOICE]}
        assert not Limitation.objects.exists()

    def test_a_missing_body_part_is_refused(self, alice: User) -> None:
        response = create(signed_in(alice), {"status": "current"})

        assert body(response) == {"body_part": [BODY_PART_CHOICE]}

    @pytest.mark.parametrize("status", ["", "chronic", "Current", 1, None])
    def test_an_unknown_status_is_refused(self, alice: User, status: Any) -> None:
        response = create(signed_in(alice), {"body_part": "knee", "status": status})

        assert body(response) == {"status": [LIMITATION_STATUS_CHOICE]}

    @pytest.mark.parametrize(
        "sports",
        [
            ["golf"],
            ["running", "running"],
            ["Running"],
            "running",
            {"running": True},
            [1],
            [None],
            [["running"]],
            None,
            5,
        ],
    )
    def test_unusable_sports_are_refused(self, alice: User, sports: Any) -> None:
        response = create(signed_in(alice), {"body_part": "knee", "sports": sports})

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert body(response) == {"sports": [LIMITATION_SPORTS_CHOICE]}
        assert not Limitation.objects.exists()

    @pytest.mark.parametrize("data", [[], "text", 5])
    def test_a_body_that_is_no_object_is_refused(self, alice: User, data: Any) -> None:
        response = create(signed_in(alice), data)

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert not Limitation.objects.exists()

    def test_every_problem_is_named_at_once(self, alice: User) -> None:
        response = create(
            signed_in(alice), {"body_part": "elbow", "status": "x", "sports": ["golf"]}
        )

        assert set(body(response)) == {"body_part", "status", "sports"}

    def test_the_messages_say_what_is_allowed(self) -> None:
        assert BODY_PART_CHOICE == (
            "Choose one of: foot, ankle, achilles, calf, shin, knee, thigh, hip, back, shoulder, "
            "other."
        )
        assert LIMITATION_STATUS_CHOICE == "Choose one of: current, healed."
        assert LIMITATION_SPORTS_CHOICE == (
            "Choose any of: running, cycling, swimming, strength, or none."
        )


class TestTheLimit:
    def test_the_limit_is_fifty(self) -> None:
        assert MAX_LIMITATIONS == 50

    def test_the_last_one_is_allowed_and_the_next_is_not(self, alice: User) -> None:
        Limitation.objects.bulk_create(
            [Limitation(owner=alice, body_part="knee") for _ in range(MAX_LIMITATIONS - 1)]
        )
        api = signed_in(alice)

        assert create(api, {"body_part": "back"}).status_code == HTTPStatus.CREATED
        response = create(api, {"body_part": "hip"})

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert body(response) == {"non_field_errors": [TOO_MANY_LIMITATIONS]}
        assert Limitation.objects.count() == MAX_LIMITATIONS

    def test_other_users_entries_do_not_count(self, alice: User, bob: User) -> None:
        Limitation.objects.bulk_create(
            [Limitation(owner=bob, body_part="knee") for _ in range(MAX_LIMITATIONS)]
        )

        assert create(signed_in(alice), {"body_part": "back"}).status_code == HTTPStatus.CREATED

    def test_deleting_one_makes_room(self, alice: User) -> None:
        entries = Limitation.objects.bulk_create(
            [Limitation(owner=alice, body_part="knee") for _ in range(MAX_LIMITATIONS)]
        )
        api = signed_in(alice)
        api.call("DELETE", detail(entries[0].pk))

        assert create(api, {"body_part": "back"}).status_code == HTTPStatus.CREATED

    def test_changing_an_entry_is_not_stopped_by_a_full_list(self, alice: User) -> None:
        entries = Limitation.objects.bulk_create(
            [Limitation(owner=alice, body_part="knee") for _ in range(MAX_LIMITATIONS)]
        )

        response = signed_in(alice).call("PATCH", detail(entries[0].pk), {"status": "healed"})

        assert response.status_code == HTTPStatus.OK


class TestChanging:
    def test_the_status_changes_and_the_rest_stays(self, alice: User) -> None:
        mine = stored(alice, body_part="achilles", sports=["running"])

        response = signed_in(alice).call("PATCH", detail(mine.pk), {"status": "healed"})

        assert response.status_code == HTTPStatus.OK
        assert body(response) == {
            "id": str(mine.pk),
            "body_part": "achilles",
            "status": "healed",
            "sports": ["running"],
        }

    def test_the_sports_can_be_changed_and_emptied(self, alice: User) -> None:
        mine = stored(alice, sports=["running"])
        api = signed_in(alice)

        assert body(api.call("PATCH", detail(mine.pk), {"sports": ["cycling", "running"]}))[
            "sports"
        ] == ["running", "cycling"]
        assert body(api.call("PATCH", detail(mine.pk), {"sports": []}))["sports"] == []

    def test_the_body_part_can_be_changed(self, alice: User) -> None:
        mine = stored(alice, body_part="knee")

        response = signed_in(alice).call("PATCH", detail(mine.pk), {"body_part": "hip"})

        assert body(response)["body_part"] == "hip"

    def test_a_refused_change_leaves_the_entry_as_it_was(self, alice: User) -> None:
        mine = stored(alice, body_part="knee", sports=["running"])

        response = signed_in(alice).call(
            "PATCH", detail(mine.pk), {"status": "healed", "sports": ["golf"]}
        )

        assert response.status_code == HTTPStatus.BAD_REQUEST
        mine.refresh_from_db()
        assert (mine.status, mine.sports) == ("current", ["running"])

    def test_the_owner_and_the_id_cannot_be_changed(self, alice: User, bob: User) -> None:
        mine = stored(alice)

        signed_in(alice).call(
            "PATCH", detail(mine.pk), {"owner": str(bob.pk), "id": str(uuid4()), "status": "healed"}
        )

        after = Limitation.objects.get()
        assert (after.pk, after.owner) == (mine.pk, alice)
        assert after.status == "healed"

    def test_a_healed_entry_can_be_made_current_again(self, alice: User) -> None:
        mine = stored(alice, status="healed")

        response = signed_in(alice).call("PATCH", detail(mine.pk), {"status": "current"})

        assert body(response)["status"] == "current"


class TestDeleting:
    def test_an_entry_is_deleted(self, alice: User) -> None:
        mine = stored(alice)
        api = signed_in(alice)

        response = api.call("DELETE", detail(mine.pk))

        assert response.status_code == HTTPStatus.NO_CONTENT
        assert not Limitation.objects.exists()
        assert api.call("GET", detail(mine.pk)).status_code == HTTPStatus.NOT_FOUND


class TestOtherUsers:
    @pytest.mark.parametrize("method", ["GET", "PATCH", "DELETE"])
    def test_another_users_entry_does_not_exist(self, alice: User, bob: User, method: str) -> None:
        theirs = stored(bob, body_part="back")

        response = signed_in(alice).call(method, detail(theirs.pk), {"status": "healed"})

        assert response.status_code == HTTPStatus.NOT_FOUND
        theirs.refresh_from_db()
        assert theirs.status == "current"

    @pytest.mark.parametrize("pk", ["1", "abc", "not-a-uuid"])
    def test_an_id_that_is_no_uuid_is_not_found(self, alice: User, pk: str) -> None:
        assert signed_in(alice).call("GET", detail(pk)).status_code == HTTPStatus.NOT_FOUND

    def test_an_unknown_uuid_is_not_found(self, alice: User) -> None:
        assert signed_in(alice).call("GET", detail(uuid4())).status_code == HTTPStatus.NOT_FOUND
