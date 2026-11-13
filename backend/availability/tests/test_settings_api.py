import json
from datetime import date, timedelta
from http import HTTPStatus
from typing import Any

import pytest

from accounts.models import User
from accounts.tests.conftest import AuthApi
from availability.capacity import minutes_in_week
from availability.models import AvailabilitySettings, WeekdayMinutes

from .conftest import make_user, signed_in

pytestmark = pytest.mark.django_db

URL = "/api/availability/"
MONDAY = date(2027, 7, 12)
EMPTY = {"weekdays": [0] * 7, "weekly_budget_minutes": None, "limitations": ""}
WEEK = [60, 0, 90, 0, 0, 120, 180]


@pytest.fixture
def alice() -> User:
    return make_user("alice@example.com")


@pytest.fixture
def bob() -> User:
    return make_user("bob@example.com")


def body(response: Any) -> Any:
    return json.loads(response.content)


def read(api: AuthApi) -> Any:
    response = api.call("GET", URL)
    assert response.status_code == HTTPStatus.OK
    return body(response)


def save(api: AuthApi, data: Any) -> Any:
    return api.call("PATCH", URL, data)


def rows() -> tuple[int, int]:
    return WeekdayMinutes.objects.count(), AvailabilitySettings.objects.count()


class TestAccess:
    @pytest.mark.parametrize("method", ["GET", "PATCH"])
    def test_anonymous_visitors_are_refused(self, method: str) -> None:
        response = AuthApi().call(method, URL, {"limitations": "x"})

        assert response.status_code == HTTPStatus.FORBIDDEN
        assert rows() == (0, 0)

    def test_a_request_without_the_csrf_token_is_refused(self, alice: User) -> None:
        api = signed_in(alice)

        response = api.client.generic(
            "PATCH", URL, data=json.dumps({"limitations": "x"}), content_type="application/json"
        )

        assert response.status_code == HTTPStatus.FORBIDDEN
        assert rows() == (0, 0)

    @pytest.mark.parametrize("method", ["PUT", "POST", "DELETE"])
    def test_other_methods_are_not_allowed(self, alice: User, method: str) -> None:
        response = signed_in(alice).call(method, URL, EMPTY)

        assert response.status_code == HTTPStatus.METHOD_NOT_ALLOWED
        assert rows() == (0, 0)


class TestReading:
    def test_a_user_who_saved_nothing_gets_zeros_and_no_budget(self, alice: User) -> None:
        assert read(signed_in(alice)) == EMPTY

    def test_reading_writes_nothing(self, alice: User) -> None:
        api = signed_in(alice)

        read(api)
        read(api)

        assert rows() == (0, 0)

    def test_the_answer_has_exactly_these_fields(self, alice: User) -> None:
        api = signed_in(alice)
        save(api, {"weekdays": WEEK, "weekly_budget_minutes": 300, "limitations": "Knee"})

        assert set(read(api)) == {"weekdays", "weekly_budget_minutes", "limitations"}

    def test_the_weekdays_come_monday_first_and_missing_ones_are_zero(self, alice: User) -> None:
        WeekdayMinutes.objects.create(owner=alice, weekday=0, minutes=60)
        WeekdayMinutes.objects.create(owner=alice, weekday=6, minutes=180)

        assert read(signed_in(alice))["weekdays"] == [60, 0, 0, 0, 0, 0, 180]

    def test_a_user_sees_only_their_own_data(self, alice: User, bob: User) -> None:
        WeekdayMinutes.objects.create(owner=bob, weekday=0, minutes=500)
        AvailabilitySettings.objects.create(
            owner=bob, weekly_budget_minutes=900, limitations="Bob's back"
        )

        assert read(signed_in(alice)) == EMPTY


class TestSaving:
    def test_everything_at_once(self, alice: User) -> None:
        api = signed_in(alice)

        response = save(
            api, {"weekdays": WEEK, "weekly_budget_minutes": 300, "limitations": "No running"}
        )

        assert response.status_code == HTTPStatus.OK
        assert body(response) == {
            "weekdays": WEEK,
            "weekly_budget_minutes": 300,
            "limitations": "No running",
        }
        assert read(api) == body(response)
        assert rows() == (7, 1)

    def test_the_weekdays_alone_leave_the_rest_as_it_was(self, alice: User) -> None:
        api = signed_in(alice)
        save(api, {"weekly_budget_minutes": 300, "limitations": "Knee"})

        save(api, {"weekdays": WEEK})

        assert read(api) == {"weekdays": WEEK, "weekly_budget_minutes": 300, "limitations": "Knee"}

    def test_the_budget_alone_leaves_the_rest_as_it_was(self, alice: User) -> None:
        api = signed_in(alice)
        save(api, {"weekdays": WEEK, "limitations": "Knee"})

        save(api, {"weekly_budget_minutes": 240})

        assert read(api) == {"weekdays": WEEK, "weekly_budget_minutes": 240, "limitations": "Knee"}

    def test_the_limitations_alone_leave_the_rest_as_it_was(self, alice: User) -> None:
        api = signed_in(alice)
        save(api, {"weekdays": WEEK, "weekly_budget_minutes": 300})

        save(api, {"limitations": "Knee"})

        assert read(api) == {"weekdays": WEEK, "weekly_budget_minutes": 300, "limitations": "Knee"}

    def test_null_removes_the_budget(self, alice: User) -> None:
        api = signed_in(alice)
        save(api, {"weekly_budget_minutes": 300})

        response = save(api, {"weekly_budget_minutes": None})

        assert body(response)["weekly_budget_minutes"] is None

    def test_a_budget_of_zero_is_a_budget(self, alice: User) -> None:
        response = save(signed_in(alice), {"weekly_budget_minutes": 0})

        assert body(response)["weekly_budget_minutes"] == 0

    def test_an_empty_request_changes_nothing_and_creates_nothing(self, alice: User) -> None:
        response = save(signed_in(alice), {})

        assert response.status_code == HTTPStatus.OK
        assert body(response) == EMPTY
        assert rows() == (0, 0)

    def test_saving_again_updates_instead_of_adding(self, alice: User) -> None:
        api = signed_in(alice)
        save(api, {"weekdays": WEEK, "weekly_budget_minutes": 300})

        save(api, {"weekdays": [30] * 7, "weekly_budget_minutes": 100})

        assert rows() == (7, 1)
        assert read(api) == {"weekdays": [30] * 7, "weekly_budget_minutes": 100, "limitations": ""}

    def test_the_limits_themselves_are_accepted(self, alice: User) -> None:
        response = save(
            signed_in(alice),
            {
                "weekdays": [0, 1440, 0, 0, 0, 0, 0],
                "weekly_budget_minutes": 10080,
                "limitations": "x" * 1000,
            },
        )

        assert response.status_code == HTTPStatus.OK

    def test_the_limitations_are_trimmed_and_may_be_emptied(self, alice: User) -> None:
        api = signed_in(alice)

        assert body(save(api, {"limitations": "  Knee  "}))["limitations"] == "Knee"
        assert body(save(api, {"limitations": ""}))["limitations"] == ""

    def test_the_limitations_are_text_never_markup(self, alice: User) -> None:
        response = save(signed_in(alice), {"limitations": "<b>x</b> & <script>1</script>"})

        assert body(response)["limitations"] == "<b>x</b> & <script>1</script>"
        assert response["Content-Type"] == "application/json"

    def test_other_fields_are_ignored(self, alice: User, bob: User) -> None:
        api = signed_in(alice)

        save(api, {"owner": str(bob.pk), "id": 7, "weekday": 3, "limitations": "Knee"})

        assert AvailabilitySettings.objects.get().owner == alice
        assert not AvailabilitySettings.objects.filter(owner=bob).exists()

    def test_saving_one_user_leaves_the_other_alone(self, alice: User, bob: User) -> None:
        bob_api = signed_in(bob)
        save(bob_api, {"weekdays": [10] * 7, "weekly_budget_minutes": 50, "limitations": "Bob"})

        save(signed_in(alice), {"weekdays": WEEK, "weekly_budget_minutes": 300})

        assert read(bob_api) == {
            "weekdays": [10] * 7,
            "weekly_budget_minutes": 50,
            "limitations": "Bob",
        }

    def test_a_failure_while_saving_leaves_the_weekdays_as_they_were(
        self, alice: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api = signed_in(alice)
        save(api, {"weekdays": WEEK})

        def broken(*args: Any, **kwargs: Any) -> None:
            raise RuntimeError("disk full")

        monkeypatch.setattr(AvailabilitySettings, "save", broken)
        with pytest.raises(RuntimeError):
            save(api, {"weekdays": [10] * 7, "limitations": "Knee"})
        monkeypatch.undo()

        assert read(api)["weekdays"] == WEEK

    def test_the_capacity_follows_what_was_saved(self, alice: User) -> None:
        api = signed_in(alice)

        save(api, {"weekdays": WEEK})
        assert minutes_in_week(alice, MONDAY) == 450

        save(api, {"weekly_budget_minutes": 200})
        assert minutes_in_week(alice, MONDAY) == 200
        assert minutes_in_week(alice, MONDAY + timedelta(days=7)) == 200


class TestRefusals:
    @pytest.mark.parametrize(
        "weekdays",
        [[0] * 6, [0] * 8, [], "0000000", {"0": 1}, 7, None, [-1, 0, 0, 0, 0, 0, 0],
         [1441, 0, 0, 0, 0, 0, 0], ["60"] * 7, [60.5] * 7, [True] * 7, [None] * 7, [[60]] * 7],
    )  # fmt: skip
    def test_unusable_weekdays_are_refused(self, alice: User, weekdays: Any) -> None:
        response = save(signed_in(alice), {"weekdays": weekdays})

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert list(body(response)) == ["weekdays"]
        assert all(isinstance(text, str) for text in body(response)["weekdays"])
        assert rows() == (0, 0)

    @pytest.mark.parametrize("budget", [-1, 10081, "300", 300.5, True, [], {}])
    def test_an_unusable_budget_is_refused(self, alice: User, budget: Any) -> None:
        response = save(signed_in(alice), {"weekly_budget_minutes": budget})

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert list(body(response)) == ["weekly_budget_minutes"]
        assert rows() == (0, 0)

    @pytest.mark.parametrize("limitations", [5, ["Knee"], None, True, {"a": 1}, "x" * 1001])
    def test_unusable_limitations_are_refused(self, alice: User, limitations: Any) -> None:
        response = save(signed_in(alice), {"limitations": limitations})

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert list(body(response)) == ["limitations"]
        assert rows() == (0, 0)

    @pytest.mark.parametrize("data", [[], "text", 5])
    def test_a_body_that_is_no_object_is_refused(self, alice: User, data: Any) -> None:
        response = save(signed_in(alice), data)

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert rows() == (0, 0)

    def test_a_json_null_is_refused(self, alice: User) -> None:
        api = signed_in(alice)

        response = api.client.generic(
            "PATCH",
            URL,
            data="null",
            content_type="application/json",
            headers={"X-CSRFToken": api._csrf_token()},
        )

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert rows() == (0, 0)

    def test_an_empty_body_is_the_same_as_no_changes(self, alice: User) -> None:
        response = signed_in(alice).call("PATCH", URL, None)

        assert response.status_code == HTTPStatus.OK
        assert body(response) == EMPTY
        assert rows() == (0, 0)

    def test_a_refusal_saves_nothing_of_the_rest(self, alice: User) -> None:
        api = signed_in(alice)
        save(api, {"weekdays": WEEK, "weekly_budget_minutes": 300, "limitations": "Knee"})

        response = save(
            api, {"weekdays": [10] * 7, "weekly_budget_minutes": 99, "limitations": "x" * 1001}
        )

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert read(api) == {"weekdays": WEEK, "weekly_budget_minutes": 300, "limitations": "Knee"}

    def test_every_problem_is_named_at_once(self, alice: User) -> None:
        response = save(
            signed_in(alice),
            {"weekdays": [0] * 3, "weekly_budget_minutes": -5, "limitations": "x" * 1001},
        )

        assert set(body(response)) == {"weekdays", "weekly_budget_minutes", "limitations"}

    def test_the_messages_say_what_is_allowed(self, alice: User) -> None:
        api = signed_in(alice)

        assert body(save(api, {"weekdays": [1]}))["weekdays"] == [
            "Enter seven numbers of minutes, Monday first."
        ]
        assert body(save(api, {"weekdays": [1441] + [0] * 6}))["weekdays"] == [
            "Enter whole minutes between 0 and 1440 for every day."
        ]
        assert body(save(api, {"weekly_budget_minutes": 10081}))["weekly_budget_minutes"] == [
            "Enter whole minutes between 0 and 10080."
        ]
