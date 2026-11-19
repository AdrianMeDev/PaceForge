import json
from datetime import UTC, datetime
from http import HTTPStatus
from typing import Any
from uuid import uuid4

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.forms.models import model_to_dict

from accounts.models import User
from activities.models import Activity, ActivityFile

from .conftest import make_user, signed_in
from .fit_builder import activity_file

pytestmark = pytest.mark.django_db

MARKER = "SECRETMARKER"
START = datetime(2026, 11, 12, 6, 30, tzinfo=UTC)


@pytest.fixture
def alice() -> User:
    return make_user("alice@example.com")


@pytest.fixture
def bob() -> User:
    return make_user("bob@example.com")


def url(activity: Activity | str) -> str:
    return f"/api/activities/{activity.pk if isinstance(activity, Activity) else activity}/"


def make(owner: User, **fields: Any) -> Activity:
    values: dict[str, Any] = {
        "source": "manual",
        "sport": "running",
        "start_time": START,
        "timer_seconds": 3600.0,
        **fields,
    }
    return Activity.objects.create(owner=owner, **values)


def rate(user: User, activity: Activity | str, **changes: Any) -> Any:
    return signed_in(user).call("PATCH", url(activity), changes)


def body(response: Any) -> Any:
    return json.loads(response.content)


def stored(activity: Activity) -> dict[str, Any]:
    return model_to_dict(Activity.objects.get(pk=activity.pk))


class TestRating:
    def test_how_hard_it_felt_and_a_note(self, alice: User) -> None:
        activity = make(alice)

        response = rate(alice, activity, rpe=6, notes="Legs were heavy")

        assert response.status_code == HTTPStatus.OK
        activity.refresh_from_db()
        assert (activity.rpe, activity.notes) == (6, "Legs were heavy")

    def test_the_answer_is_the_detail_of_the_activity_with_the_load_that_follows(
        self, alice: User
    ) -> None:
        activity = make(alice)

        data = body(rate(alice, activity, rpe=6))

        assert data["id"] == str(activity.pk)
        assert (data["rpe"], data["load"]) == (6, 60)  # 60 minutes at 6 × 10/h
        assert data["laps"] == []
        assert "source_hash" not in data and "owner" not in data

    def test_only_what_is_sent_changes(self, alice: User) -> None:
        activity = make(alice, rpe=4, notes="first")

        rate(alice, activity, rpe=8)
        activity.refresh_from_db()
        assert (activity.rpe, activity.notes) == (8, "first")

        rate(alice, activity, notes="second")
        activity.refresh_from_db()
        assert (activity.rpe, activity.notes) == (8, "second")

    def test_the_rating_and_the_note_can_be_cleared(self, alice: User) -> None:
        activity = make(alice, rpe=4, notes="first")

        data = body(rate(alice, activity, rpe=None, notes=""))

        activity.refresh_from_db()
        assert (activity.rpe, activity.notes) == (None, "")
        assert (data["rpe"], data["notes"], data["load"]) == (None, "", None)

    def test_an_imported_activity_can_be_rated_and_nothing_else_of_it_changes(
        self, alice: User
    ) -> None:
        api = signed_in(alice)
        created = api.client.post(
            "/api/activities/import/",
            {"file": SimpleUploadedFile("run.fit", activity_file())},
            headers={"X-CSRFToken": api._csrf_token()},
        )
        assert created.status_code == HTTPStatus.CREATED
        activity = Activity.objects.get()
        before = stored(activity)

        response = api.call("PATCH", url(activity), {"rpe": 7, "notes": "Hilly"})

        assert response.status_code == HTTPStatus.OK
        after = stored(activity)
        assert {key for key in before if before[key] != after[key]} == {"rpe", "notes"}
        assert ActivityFile.objects.get(activity=activity).read() == activity_file()

    @pytest.mark.parametrize("value", [1, 5, 10])
    def test_every_rating_from_one_to_ten(self, alice: User, value: int) -> None:
        assert rate(alice, make(alice), rpe=value).status_code == HTTPStatus.OK

    def test_a_note_up_to_the_limit_and_with_several_lines(self, alice: User) -> None:
        activity = make(alice)

        assert rate(alice, activity, notes="n" * 500).status_code == HTTPStatus.OK
        assert rate(alice, activity, notes="one\ntwo").status_code == HTTPStatus.OK
        activity.refresh_from_db()
        assert activity.notes == "one\ntwo"


class TestRefusals:
    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("rpe", 0),
            ("rpe", 11),
            ("rpe", -1),
            ("rpe", 5.5),
            ("rpe", "7"),
            ("rpe", True),
            ("rpe", [7]),
            ("notes", "x" * 501),
            ("notes", 5),
            ("notes", None),
            ("notes", ["a"]),
            ("notes", "bell\x07"),
            ("notes", "null\x00byte"),
            ("notes", "reversed \u202etext"),
            ("notes", "line\u2028separator"),
        ],
    )
    def test_a_value_that_does_not_fit_is_refused_and_nothing_changes(
        self, alice: User, field: str, value: Any
    ) -> None:
        activity = make(alice, rpe=3, notes="kept")
        before = stored(activity)

        response = rate(alice, activity, **{field: value})

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert field in body(response)
        assert stored(activity) == before

    @pytest.mark.parametrize(
        "field",
        ["sport", "start_time", "timer_seconds", "distance_m", "load", "source", "owner", "id"],
    )
    def test_any_other_field_is_refused_even_next_to_a_good_rating(
        self, alice: User, field: str
    ) -> None:
        activity = make(alice, rpe=3)
        before = stored(activity)

        response = rate(alice, activity, rpe=9, **{field: "cycling"})

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert body(response) == {
            "non_field_errors": ["Only the rating (rpe) and the note (notes) can be changed."]
        }
        assert stored(activity) == before

    def test_nothing_to_change_is_refused(self, alice: User) -> None:
        activity = make(alice)

        response = rate(alice, activity)

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert "non_field_errors" in body(response)

    def test_a_body_that_is_no_object_is_refused(self, alice: User) -> None:
        activity = make(alice)
        api = signed_in(alice)

        response = api.client.generic(
            "PATCH",
            url(activity),
            data=json.dumps([5]),
            content_type="application/json",
            headers={"X-CSRFToken": api._csrf_token()},
        )

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert stored(activity)["rpe"] is None

    def test_every_problem_is_reported_at_once(self, alice: User) -> None:
        response = rate(alice, make(alice), rpe=11, notes="x" * 501)

        assert set(body(response)) == {"rpe", "notes"}

    def test_nothing_of_the_input_is_repeated_in_an_error(self, alice: User) -> None:
        activity = make(alice)

        for changes in (
            {"rpe": MARKER, "notes": MARKER + "\x00"},
            {"rpe": 5, MARKER: MARKER},
            {"notes": MARKER * 100},
        ):
            response = rate(alice, activity, **changes)

            assert response.status_code == HTTPStatus.BAD_REQUEST
            assert MARKER not in response.content.decode()


class TestAccess:
    def test_another_users_activity_does_not_exist_and_is_left_alone(
        self, alice: User, bob: User
    ) -> None:
        mine = make(alice, rpe=3, notes="mine")
        before = stored(mine)

        response = rate(bob, mine, rpe=9, notes="bob was here")

        assert response.status_code == HTTPStatus.NOT_FOUND
        assert stored(mine) == before

    @pytest.mark.parametrize("ident", ["not-a-uuid", "12345"])
    def test_an_id_that_is_no_uuid_is_a_404(self, alice: User, ident: str) -> None:
        assert rate(alice, ident, rpe=5).status_code == HTTPStatus.NOT_FOUND

    def test_an_unknown_id_is_a_404(self, alice: User) -> None:
        assert rate(alice, str(uuid4()), rpe=5).status_code == HTTPStatus.NOT_FOUND

    def test_a_patch_without_the_csrf_token_is_refused(self, alice: User) -> None:
        activity = make(alice)
        api = signed_in(alice)

        response = api.client.generic(
            "PATCH", url(activity), data=json.dumps({"rpe": 5}), content_type="application/json"
        )

        assert response.status_code == HTTPStatus.FORBIDDEN
        activity.refresh_from_db()
        assert activity.rpe is None

    def test_a_put_is_still_not_allowed(self, alice: User) -> None:
        activity = make(alice)

        response = signed_in(alice).call("PUT", url(activity), {"rpe": 5})

        assert response.status_code == HTTPStatus.METHOD_NOT_ALLOWED
