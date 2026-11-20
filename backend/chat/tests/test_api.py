import json
from collections.abc import Callable
from http import HTTPStatus
from typing import Any

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from accounts.models import User
from accounts.tests.conftest import AuthApi
from chat.models import USER_TEXT_MAX, ChatMessage
from coach.models import AIProviderConfiguration
from coach.providers.base import InvalidKeyError, ProviderUnavailableError, RateLimitedError
from coach.views import PROBLEMS
from goals import services as goal_services
from planning.models import PlannedWorkout
from planning.tests.scripted import Scripted
from reviews.tests.builders import MONDAY, NOW, make_plan
from reviews.tests.conftest import signed_in
from season.models import SeasonPlanVersion

pytestmark = pytest.mark.django_db

URL = "/api/chat/messages/"
KEY = "synthetic-test-token-abcdefghij"
MARKER = "SECRETMARKER"


@pytest.fixture(autouse=True)
def _clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(goal_services, "_utc_now", lambda: NOW)


@pytest.fixture
def athlete(alice: User) -> User:
    AIProviderConfiguration.objects.create(
        owner=alice, provider="anthropic", model="claude-sonnet-5-5", api_key=KEY
    )
    make_plan(alice, MONDAY, workouts=7)
    return alice


def said(reply: str = "Done.", actions: list[dict[str, Any]] | None = None) -> str:
    return json.dumps({"reply": reply, "actions": actions or []})


def write(user: User, text: object = "Hi") -> Any:
    return signed_in(user).call("POST", URL, {"text": text})


def body(response: Any) -> Any:
    return json.loads(response.content)


class TestWriting:
    def test_the_answer_is_the_two_messages_that_were_stored(
        self, athlete: User, provide: Callable[..., Scripted]
    ) -> None:
        provide(said("Fine."))

        response = write(athlete, "How is my week?")

        assert response.status_code == HTTPStatus.CREATED
        first, second = body(response)["messages"]
        assert (first["role"], first["text"]) == ("user", "How is my week?")
        assert (second["role"], second["text"]) == ("coach", "Fine.")
        assert second["plan"] is None and second["changes"] == []
        assert second["season_plan"] is None
        assert first["created_at"] and first["id"] != second["id"]
        # the same as the GET shows afterwards
        assert body(signed_in(athlete).call("GET", URL)) == body(response)

    def test_a_change_names_the_draft_and_tells_what_changed(
        self, athlete: User, provide: Callable[..., Scripted]
    ) -> None:
        saturday = PlannedWorkout.objects.for_user(athlete).get(day="2026-11-14")
        provide(
            said(
                "Sunday then.",
                [{"tool": "move_workout", "id": str(saturday.lineage), "day": "2026-11-15"}],
            )
        )

        coach = body(write(athlete, "Rain on Saturday"))["messages"][1]

        assert coach["changes"] == ["Run on Sat (60 min) moved to Sun"]
        assert coach["plan"]["week_start"] == MONDAY.isoformat()
        assert coach["season_plan"] is None

    def test_the_text_is_shown_as_it_was_written(
        self, athlete: User, provide: Callable[..., Scripted]
    ) -> None:
        provide(said("A <b>fine</b> week."))

        messages = body(write(athlete, "<script>x</script>"))["messages"]

        assert messages[0]["text"] == "<script>x</script>"
        assert messages[1]["text"] == "A <b>fine</b> week."

    @pytest.mark.parametrize("text", ["", "   ", "x" * (USER_TEXT_MAX + 1), 7, None, ["a"]])
    def test_a_message_that_cannot_be_used_is_refused(
        self, athlete: User, provide: Callable[..., Scripted], text: object
    ) -> None:
        scripted = provide(said())

        response = write(athlete, text)

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert body(response)["code"] == "invalid"
        assert scripted.calls == [] and ChatMessage.objects.count() == 0

    def test_a_body_that_is_no_object_is_refused(self, athlete: User) -> None:
        response = signed_in(athlete).call("POST", URL)

        assert response.status_code == HTTPStatus.BAD_REQUEST

    def test_without_a_provider(self, alice: User) -> None:
        response = write(alice)

        assert response.status_code == HTTPStatus.CONFLICT
        assert body(response)["code"] == "not_configured"
        assert ChatMessage.objects.count() == 0

    @pytest.mark.parametrize(
        ("error", "http_status", "code"),
        [
            (InvalidKeyError("x"), HTTPStatus.BAD_GATEWAY, "invalid_key"),
            (RateLimitedError("x"), HTTPStatus.TOO_MANY_REQUESTS, "rate_limited"),
            (ProviderUnavailableError("x"), HTTPStatus.SERVICE_UNAVAILABLE, "unavailable"),
        ],
    )
    def test_a_provider_that_fails_gives_a_fixed_text(
        self,
        athlete: User,
        provide: Callable[..., Scripted],
        error: Exception,
        http_status: int,
        code: str,
    ) -> None:
        provide(type(error)(f"{MARKER} {KEY}"))

        response = write(athlete)

        assert response.status_code == http_status
        assert body(response)["code"] == code
        assert body(response)["detail"] == PROBLEMS[code]
        assert MARKER not in response.content.decode() and KEY not in response.content.decode()
        assert ChatMessage.objects.count() == 0

    def test_is_rate_limited(self, athlete: User, provide: Callable[..., Scripted]) -> None:
        provide(*[said() for _ in range(11)])
        api = signed_in(athlete)

        statuses = [api.call("POST", URL, {"text": "Hi"}).status_code for _ in range(11)]

        assert statuses[:10] == [HTTPStatus.CREATED] * 10
        assert statuses[10] == HTTPStatus.TOO_MANY_REQUESTS


class TestReading:
    def test_an_empty_conversation(self, alice: User) -> None:
        assert body(signed_in(alice).call("GET", URL)) == {"messages": []}

    def test_each_user_sees_only_their_own(
        self, athlete: User, bob: User, provide: Callable[..., Scripted]
    ) -> None:
        provide(said())
        write(athlete, "Mine")
        ChatMessage.objects.create(owner=bob, role="user", text="Bob's")

        texts = [m["text"] for m in body(signed_in(athlete).call("GET", URL))["messages"]]

        assert texts == ["Mine", "Done."]

    def test_an_answer_names_the_season_draft_it_made(
        self, athlete: User, provide: Callable[..., Scripted]
    ) -> None:
        provide(said("Fine."))
        season = SeasonPlanVersion.objects.create(owner=athlete, version=2)
        ChatMessage.objects.create(
            owner=athlete, role="coach", text="Season changed.", season_plan=season, changes=["y"]
        )

        messages = body(signed_in(athlete).call("GET", URL))["messages"]

        assert messages[-1]["season_plan"] == {"id": str(season.pk), "version": 2}
        assert messages[-1]["plan"] is None

    def test_another_users_season_drafts_are_never_listed(self, athlete: User, bob: User) -> None:
        season = SeasonPlanVersion.objects.create(owner=bob)
        ChatMessage.objects.create(
            owner=bob, role="coach", text="Bob's season.", season_plan=season, changes=["y"]
        )

        messages = body(signed_in(athlete).call("GET", URL))["messages"]

        assert messages == []

    def test_the_number_of_queries_does_not_depend_on_the_messages(self, athlete: User) -> None:
        api = signed_in(athlete)
        with CaptureQueriesContext(connection) as few:
            api.call("GET", URL)
        plan = make_plan(athlete, MONDAY, status="draft")
        season = SeasonPlanVersion.objects.create(owner=athlete)
        for n in range(30):
            ChatMessage.objects.create(
                owner=athlete, role="coach", text=f"m{n}", plan=plan, changes=["x"]
            )
            ChatMessage.objects.create(
                owner=athlete, role="coach", text=f"s{n}", season_plan=season, changes=["y"]
            )
        with CaptureQueriesContext(connection) as many:
            api.call("GET", URL)

        assert len(few) == len(many)


class TestDeleting:
    def test_deletes_only_the_own_conversation(self, athlete: User, bob: User) -> None:
        ChatMessage.objects.create(owner=athlete, role="user", text="Mine")
        ChatMessage.objects.create(owner=bob, role="user", text="Bob's")

        response = signed_in(athlete).call("DELETE", URL)

        assert response.status_code == HTTPStatus.NO_CONTENT
        assert [m.owner for m in ChatMessage.objects.all()] == [bob]


class TestWhoMayCome:
    @pytest.mark.parametrize("method", ["GET", "POST", "DELETE"])
    def test_anonymous_visitors_are_refused(self, method: str) -> None:
        assert AuthApi().call(method, URL).status_code == HTTPStatus.FORBIDDEN

    @pytest.mark.parametrize("method", ["POST", "DELETE"])
    def test_a_request_without_the_csrf_token_is_refused(
        self, athlete: User, provide: Callable[..., Scripted], method: str
    ) -> None:
        scripted = provide(said())
        api = signed_in(athlete)

        response = api.client.generic(method, URL, data="{}", content_type="application/json")

        assert response.status_code == HTTPStatus.FORBIDDEN
        assert scripted.calls == []

    @pytest.mark.parametrize("method", ["PUT", "PATCH"])
    def test_other_methods_are_not_allowed(self, athlete: User, method: str) -> None:
        assert signed_in(athlete).call(method, URL).status_code == HTTPStatus.METHOD_NOT_ALLOWED
