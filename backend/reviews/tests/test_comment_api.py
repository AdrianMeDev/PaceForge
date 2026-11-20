import json
from collections.abc import Callable
from datetime import timedelta
from http import HTTPStatus
from typing import Any

import pytest

from accounts.models import User
from accounts.tests.conftest import AuthApi
from coach.models import AIProviderConfiguration, AIUsageRecord
from coach.providers.base import (
    EndpointNotAllowedError,
    InvalidKeyError,
    ProviderUnavailableError,
    RateLimitedError,
    UnexpectedResponseError,
)
from coach.views import PROBLEMS
from goals import services as goal_services
from planning.tests.scripted import Scripted
from reviews.models import WeekComment

from .builders import MONDAY, NOW, make_activity, make_plan
from .conftest import make_user, signed_in

pytestmark = pytest.mark.django_db

MARKER = "SECRETMARKER"
KEY = "synthetic-test-token-abcdefghij"
COMMENT = f"/api/reviews/weeks/{MONDAY}/comment/"


@pytest.fixture(autouse=True)
def _clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(goal_services, "_utc_now", lambda: NOW)


@pytest.fixture
def alice() -> User:
    user = make_user("alice@example.com")
    AIProviderConfiguration.objects.create(
        owner=user, provider="anthropic", model="claude-sonnet-5-5", api_key=KEY
    )
    make_plan(user, workouts=2)
    make_activity(user, "2026-11-09T07:00", rpe=6)
    return user


@pytest.fixture
def bob() -> User:
    return make_user("bob@example.com")


def good(comment: str = "A steady week.", next_week: str = "hold") -> str:
    return json.dumps({"comment": comment, "next_week": next_week})


def ask(user: User, url: str = COMMENT) -> Any:
    return signed_in(user).call("POST", url)


def body(response: Any) -> Any:
    return json.loads(response.content)


class TestAsking:
    def test_the_answer_is_the_whole_week_with_the_comment_in_it(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        provide(good("One of two done.", "reduce"))

        response = ask(alice)

        assert response.status_code == HTTPStatus.CREATED
        data = body(response)
        assert data["week_start"] == MONDAY.isoformat()
        assert data["comment"]["comment"] == "One of two done."
        assert data["comment"]["next_week"] == "reduce"
        assert data["comment"]["created_at"]
        assert len(data["workouts"]) == 2 and len(data["activities"]) == 1
        # the same as the GET shows afterwards
        assert data == body(signed_in(alice).call("GET", f"/api/reviews/weeks/{MONDAY}/"))

    def test_the_comment_is_stored_and_the_call_recorded(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        provide(good())

        ask(alice)

        assert WeekComment.objects.get().owner == alice
        (record,) = AIUsageRecord.objects.all()
        assert (record.owner, record.purpose, record.outcome) == (alice, "week_review", "success")

    def test_asking_again_replaces_the_comment(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        provide(good("First."), good("Second.", "increase"))

        ask(alice)
        data = body(ask(alice))

        assert (data["comment"]["comment"], data["comment"]["next_week"]) == ("Second.", "increase")
        assert WeekComment.objects.count() == 1

    def test_a_comment_is_shown_as_the_coach_wrote_it(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        provide(good("A <b>fine</b> week.\nSee you."))

        assert body(ask(alice))["comment"]["comment"] == "A <b>fine</b> week.\nSee you."

    def test_an_earlier_week_can_be_asked_about(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        before = MONDAY - timedelta(weeks=1)
        make_plan(alice, before, workouts=1)
        provide(good())

        response = ask(alice, f"/api/reviews/weeks/{before}/comment/")

        assert response.status_code == HTTPStatus.CREATED
        assert WeekComment.objects.get().week_start == before


class TestWhatStopsItBeforeTheCall:
    @pytest.mark.parametrize(
        "week",
        ["2026-11-10", "2026-11-16", "2026-10-05", "2026-02-30", "nonsense", "20261109"],
    )
    def test_a_week_that_cannot_be_reviewed_is_a_404_with_a_fixed_text(
        self, alice: User, provide: Callable[..., Scripted], week: str
    ) -> None:
        scripted = provide(good())

        response = ask(alice, f"/api/reviews/weeks/{week}/comment/")

        assert response.status_code == HTTPStatus.NOT_FOUND
        assert body(response) == {
            "detail": "This week cannot be reviewed.",
            "code": "week_not_reviewable",
        }
        assert scripted.calls == [] and not AIUsageRecord.objects.exists()

    def test_nothing_of_the_request_is_repeated(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        provide(good())

        response = ask(alice, f"/api/reviews/weeks/{MARKER}/comment/")

        assert response.status_code == HTTPStatus.NOT_FOUND
        assert MARKER not in response.content.decode()

    def test_a_week_with_nothing_in_it_is_a_conflict_that_costs_nothing(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        scripted = provide(good())

        response = ask(alice, f"/api/reviews/weeks/{MONDAY - timedelta(weeks=1)}/comment/")

        assert response.status_code == HTTPStatus.CONFLICT
        assert body(response) == {
            "detail": "There is nothing to look back on in this week yet.",
            "code": "nothing_to_review",
        }
        assert scripted.calls == [] and not AIUsageRecord.objects.exists()

    def test_the_data_of_another_user_is_nothing_to_look_back_on(
        self, alice: User, bob: User, provide: Callable[..., Scripted]
    ) -> None:
        before = MONDAY - timedelta(weeks=1)
        make_plan(bob, before, workouts=3)
        scripted = provide(good())

        response = ask(alice, f"/api/reviews/weeks/{before}/comment/")

        assert response.status_code == HTTPStatus.CONFLICT
        assert scripted.calls == []

    def test_without_a_provider_it_is_a_conflict(self, bob: User) -> None:
        make_plan(bob, workouts=1)

        response = ask(bob)

        assert response.status_code == HTTPStatus.CONFLICT
        assert body(response) == {"detail": "No AI provider is set up.", "code": "not_configured"}

    def test_the_two_conflicts_are_told_apart(self, alice: User, bob: User) -> None:
        # alice has a provider but nothing to look back on in that week; bob the other way round
        make_plan(bob, workouts=1)
        before = f"/api/reviews/weeks/{MONDAY - timedelta(weeks=1)}/comment/"

        nothing = body(ask(alice, before))["code"]
        no_provider = body(ask(bob))["code"]

        assert (nothing, no_provider) == ("nothing_to_review", "not_configured")


class TestWhenTheCoachFails:
    @pytest.mark.parametrize(
        ("error", "http_status", "code"),
        [
            (InvalidKeyError(f"{MARKER} {KEY}"), 502, "invalid_key"),
            (ProviderUnavailableError(f"{MARKER} {KEY}"), 503, "unavailable"),
            (UnexpectedResponseError(f"{MARKER} {KEY}"), 502, "unexpected"),
            (EndpointNotAllowedError(f"{MARKER} {KEY}"), 502, "not_allowed"),
        ],
    )
    def test_a_provider_problem_has_its_own_status_and_a_fixed_text(
        self,
        alice: User,
        provide: Callable[..., Scripted],
        error: Exception,
        http_status: int,
        code: str,
    ) -> None:
        provide(error)

        response = ask(alice)

        assert response.status_code == http_status
        assert body(response) == {"detail": PROBLEMS[code], "code": code}
        assert MARKER not in response.content.decode() and KEY not in response.content.decode()
        assert not WeekComment.objects.exists()

    def test_rate_limiting_says_how_long_to_wait(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        provide(RateLimitedError(MARKER, 17))

        response = ask(alice)

        assert response.status_code == HTTPStatus.TOO_MANY_REQUESTS
        assert response["Retry-After"] == "17"
        assert body(response) == {
            "detail": PROBLEMS["rate_limited"],
            "code": "rate_limited",
            "retry_after": 17,
        }

    def test_an_answer_that_cannot_be_used_is_unprocessable_and_says_only_what_was_wrong(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        provide(f"{MARKER} no", json.dumps({"comment": "ok", "next_week": MARKER}))

        response = ask(alice)

        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert body(response) == {
            "detail": "The coach did not give a comment that can be used. Please try again.",
            "code": "not_usable",
            "problems": [
                {"path": "next_week", "message": 'Use one of "increase", "hold", "reduce".'}
            ],
        }
        assert MARKER not in response.content.decode()
        assert not WeekComment.objects.exists()


class TestTheLimit:
    def test_the_sixth_request_within_a_minute_is_throttled_before_the_provider(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        scripted = provide(*[good() for _ in range(6)])
        api = signed_in(alice)

        statuses = [api.call("POST", COMMENT).status_code for _ in range(6)]

        assert statuses == [201] * 5 + [429]
        assert len(scripted.calls) == 5

    def test_the_counter_is_its_own_and_reading_is_not_limited(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        provide(*[good() for _ in range(5)])
        api = signed_in(alice)
        for _ in range(5):
            api.call("POST", COMMENT)

        assert api.call("GET", f"/api/reviews/weeks/{MONDAY}/").status_code == 200
        assert api.call("PUT", f"/api/reviews/weeks/{MONDAY}/feedback/", {}).status_code == 200
        assert api.call("GET", "/api/planning/weeks/").status_code == 200

    def test_the_limit_is_per_user(
        self, alice: User, bob: User, provide: Callable[..., Scripted]
    ) -> None:
        provide(*[good() for _ in range(6)])
        for _ in range(5):
            ask(alice)

        assert ask(alice).status_code == HTTPStatus.TOO_MANY_REQUESTS
        # bob has no provider: he gets his conflict, not the limit of alice
        assert ask(bob).status_code == HTTPStatus.CONFLICT


class TestAccess:
    def test_anonymous_visitors_are_refused(self, provide: Callable[..., Scripted]) -> None:
        scripted = provide(good())

        response = AuthApi().call("POST", COMMENT)

        assert response.status_code == HTTPStatus.FORBIDDEN
        assert scripted.calls == []

    def test_a_post_without_the_csrf_token_is_refused(
        self, alice: User, provide: Callable[..., Scripted]
    ) -> None:
        scripted = provide(good())
        api = signed_in(alice)

        response = api.client.generic("POST", COMMENT, data="{}", content_type="application/json")

        assert response.status_code == HTTPStatus.FORBIDDEN
        assert scripted.calls == []

    @pytest.mark.parametrize("method", ["GET", "PUT", "PATCH", "DELETE"])
    def test_other_methods_are_not_allowed(self, alice: User, method: str) -> None:
        response = signed_in(alice).call(method, COMMENT)

        assert response.status_code == HTTPStatus.METHOD_NOT_ALLOWED
