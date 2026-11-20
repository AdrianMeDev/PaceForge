import json
from datetime import timedelta
from http import HTTPStatus
from typing import Any

import pytest
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from accounts.models import User
from accounts.tests.conftest import AuthApi
from goals import services as goal_services
from reviews.models import WeekFeedback

from .builders import MONDAY, NOW
from .conftest import make_user, signed_in

pytestmark = pytest.mark.django_db

MARKER = "SECRETMARKER"
FEEDBACK = f"/api/reviews/weeks/{MONDAY}/feedback/"
# A Monday that is too long ago to be reviewed.
LONG_AGO = MONDAY - timedelta(weeks=10)


@pytest.fixture(autouse=True)
def _clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(goal_services, "_utc_now", lambda: NOW)


@pytest.fixture
def alice() -> User:
    return make_user("alice@example.com")


@pytest.fixture
def bob() -> User:
    return make_user("bob@example.com")


def give_to(user: User, url: str, form: dict[str, Any]) -> Any:
    return signed_in(user).call("PUT", url, form)


def give(user: User, **form: Any) -> Any:
    return give_to(user, FEEDBACK, form)


def body(response: Any) -> Any:
    return json.loads(response.content)


FULL: dict[str, Any] = {"fatigue": 4, "motivation": 2, "pain": 1, "notes": "Heavy legs"}


class TestGiving:
    def test_the_feedback_is_stored_and_the_week_comes_back_with_it(self, alice: User) -> None:
        response = give(alice, **FULL)

        assert response.status_code == HTTPStatus.OK
        data = body(response)
        assert data["week_start"] == MONDAY.isoformat()
        assert {key: data["feedback"][key] for key in FULL} == FULL
        stored = WeekFeedback.objects.get()
        assert (stored.owner, stored.week_start) == (alice, MONDAY)
        assert (stored.fatigue, stored.motivation, stored.pain, stored.notes) == (
            4,
            2,
            1,
            "Heavy legs",
        )

    def test_the_answer_is_the_whole_week_as_the_get_shows_it(self, alice: User) -> None:
        answer = body(give(alice, **FULL))

        api = signed_in(alice)
        assert answer == body(api.call("GET", f"/api/reviews/weeks/{MONDAY}/"))

    def test_the_next_feedback_replaces_the_last_one(self, alice: User) -> None:
        give(alice, **FULL)

        give(alice, fatigue=1)

        stored = WeekFeedback.objects.get()
        assert (stored.fatigue, stored.motivation, stored.pain, stored.notes) == (1, None, None, "")

    @pytest.mark.parametrize("field", ["fatigue", "motivation", "pain"])
    @pytest.mark.parametrize("value", [1, 3, 5])
    def test_every_value_of_every_scale(self, alice: User, field: str, value: int) -> None:
        assert give(alice, **{field: value}).status_code == HTTPStatus.OK
        assert getattr(WeekFeedback.objects.get(), field) == value

    def test_a_note_alone_with_several_lines_and_up_to_the_limit(self, alice: User) -> None:
        assert give(alice, notes="one\ntwo").status_code == HTTPStatus.OK
        assert WeekFeedback.objects.get().notes == "one\ntwo"
        assert give(alice, notes="n" * 500).status_code == HTTPStatus.OK

    def test_a_scale_can_be_cleared_with_null(self, alice: User) -> None:
        give(alice, **FULL)

        give(alice, fatigue=None, motivation=2, pain=None, notes="")

        stored = WeekFeedback.objects.get()
        assert (stored.fatigue, stored.motivation, stored.pain) == (None, 2, None)

    @pytest.mark.parametrize("word", ["bad", "fair", "good", "strong"])
    def test_every_verdict_is_stored_and_comes_back(self, alice: User, word: str) -> None:
        response = give(alice, verdict=word)

        assert response.status_code == HTTPStatus.OK
        assert body(response)["feedback"]["verdict"] == word
        assert WeekFeedback.objects.get().verdict == word

    def test_a_verdict_alone_is_feedback(self, alice: User) -> None:
        give(alice, verdict="good")

        assert WeekFeedback.objects.count() == 1

    def test_no_verdict_comes_back_as_null(self, alice: User) -> None:
        response = give(alice, fatigue=3)

        assert body(response)["feedback"]["verdict"] is None
        assert WeekFeedback.objects.get().verdict == ""

    def test_the_verdict_can_be_cleared_with_null_and_by_leaving_it_out(self, alice: User) -> None:
        give(alice, fatigue=3, verdict="bad")
        give(alice, fatigue=3, verdict=None)
        assert WeekFeedback.objects.get().verdict == ""

        give(alice, fatigue=3, verdict="good")
        give(alice, fatigue=3)
        assert WeekFeedback.objects.get().verdict == ""

    def test_a_verdict_that_is_none_of_the_four_is_refused(self, alice: User) -> None:
        for value in ("great", "", "GOOD", " good", 3, True, ["good"], {"a": 1}):
            response = give(alice, fatigue=2, verdict=value)

            assert response.status_code == HTTPStatus.BAD_REQUEST, value
            assert set(body(response)) == {"verdict"}, value
        assert WeekFeedback.objects.count() == 0

    def test_feedback_with_nothing_in_it_is_removed(self, alice: User) -> None:
        give(alice, **FULL)

        response = give(alice)

        assert response.status_code == HTTPStatus.OK
        assert body(response)["feedback"] is None
        assert WeekFeedback.objects.count() == 0
        assert give(alice, fatigue=None, notes="").status_code == HTTPStatus.OK

    def test_every_week_that_can_be_reviewed_takes_feedback(self, alice: User) -> None:
        weeks = [
            week["week_start"]
            for week in body(signed_in(alice).call("GET", "/api/reviews/weeks/"))["weeks"]
        ]

        for week in weeks:
            assert (
                give_to(alice, f"/api/reviews/weeks/{week}/feedback/", {"pain": 2}).status_code
                == 200
            )
        assert WeekFeedback.objects.count() == len(weeks) == 5

    def test_the_feedback_of_another_user_is_left_alone(self, alice: User, bob: User) -> None:
        WeekFeedback.objects.create(owner=bob, week_start=MONDAY, fatigue=5, notes="bobs")

        give(alice, fatigue=1)
        give(alice)

        theirs = WeekFeedback.objects.get(owner=bob)
        assert (theirs.fatigue, theirs.notes) == (5, "bobs")


class TestRefusals:
    @pytest.mark.parametrize("field", ["fatigue", "motivation", "pain"])
    @pytest.mark.parametrize("value", [0, 6, -1, 2.5, "3", True, [3]])
    def test_a_scale_value_that_does_not_fit_is_refused_and_nothing_changes(
        self, alice: User, field: str, value: Any
    ) -> None:
        WeekFeedback.objects.create(owner=alice, week_start=MONDAY, pain=3)

        response = give(alice, **{field: value})

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert field in body(response)
        assert WeekFeedback.objects.get().pain == 3

    @pytest.mark.parametrize(
        "note",
        [
            "x" * 501,
            5,
            None,
            ["a"],
            "bell\x07",
            "null\x00byte",
            "reversed ‮text",
            "line separator",
        ],
    )
    def test_a_note_that_does_not_fit_is_refused(self, alice: User, note: Any) -> None:
        response = give(alice, notes=note)

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert "notes" in body(response)
        assert WeekFeedback.objects.count() == 0

    def test_every_problem_is_reported_at_once(self, alice: User) -> None:
        response = give(alice, fatigue=0, motivation=9, verdict="x", notes="x" * 501)

        assert set(body(response)) == {"fatigue", "motivation", "verdict", "notes"}

    @pytest.mark.parametrize("extra", ["owner", "id", "week_start", "tiredness"])
    def test_a_field_that_is_not_part_of_the_form_is_refused(self, alice: User, extra: str) -> None:
        response = give(alice, fatigue=2, **{extra: "x"})

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert body(response) == {"non_field_errors": ["Only the fields of this form can be sent."]}
        assert WeekFeedback.objects.count() == 0

    def test_a_body_that_is_no_object_is_refused(self, alice: User) -> None:
        api = signed_in(alice)

        response = api.client.generic(
            "PUT",
            FEEDBACK,
            data=json.dumps([3]),
            content_type="application/json",
            headers={"X-CSRFToken": api._csrf_token()},
        )

        assert response.status_code == HTTPStatus.BAD_REQUEST

    def test_nothing_of_the_input_is_repeated_in_an_error(self, alice: User) -> None:
        for form in (
            {
                "fatigue": MARKER,
                "motivation": MARKER,
                "pain": MARKER,
                "verdict": MARKER,
                "notes": MARKER + "\x00",
            },
            {MARKER: MARKER},
            {"notes": MARKER * 100},
        ):
            response = give(alice, **form)

            assert response.status_code == HTTPStatus.BAD_REQUEST
            assert MARKER not in response.content.decode()

    @pytest.mark.parametrize(
        "week", ["2026-11-10", "2026-11-16", "2026-10-05", "2026-02-30", "nonsense", "20261109"]
    )
    def test_a_week_that_cannot_be_reviewed_is_a_404(self, alice: User, week: str) -> None:
        response = give_to(alice, f"/api/reviews/weeks/{week}/feedback/", {"fatigue": 2})

        assert response.status_code == HTTPStatus.NOT_FOUND
        assert body(response)["code"] == "week_not_reviewable"
        assert WeekFeedback.objects.count() == 0

    def test_a_week_that_cannot_be_reviewed_is_not_cleared_either(self, alice: User) -> None:
        WeekFeedback.objects.create(owner=alice, week_start=LONG_AGO, fatigue=2)

        give_to(alice, f"/api/reviews/weeks/{LONG_AGO}/feedback/", {})

        assert WeekFeedback.objects.count() == 1


class TestAccess:
    def test_anonymous_visitors_are_refused(self) -> None:
        response = AuthApi().call("PUT", FEEDBACK, FULL)

        assert response.status_code == HTTPStatus.FORBIDDEN
        assert WeekFeedback.objects.count() == 0

    def test_anonymous_visitors_are_refused_when_apiview_defaults_allow_any(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(APIView, "permission_classes", [AllowAny])

        response = AuthApi().call("PUT", FEEDBACK, FULL)

        assert response.status_code == HTTPStatus.FORBIDDEN
        assert not WeekFeedback.objects.exists()

    def test_a_put_without_the_csrf_token_is_refused(self, alice: User) -> None:
        api = signed_in(alice)

        response = api.client.generic(
            "PUT", FEEDBACK, data=json.dumps(FULL), content_type="application/json"
        )

        assert response.status_code == HTTPStatus.FORBIDDEN
        assert WeekFeedback.objects.count() == 0

    @pytest.mark.parametrize("method", ["GET", "POST", "PATCH", "DELETE"])
    def test_other_methods_are_not_allowed(self, alice: User, method: str) -> None:
        response = signed_in(alice).call(method, FEEDBACK, {})

        assert response.status_code == HTTPStatus.METHOD_NOT_ALLOWED
