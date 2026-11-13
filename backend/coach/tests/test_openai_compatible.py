import json
import logging
import traceback
from typing import Any

import pytest

from accounts.models import User
from coach.models import AIProviderConfiguration
from coach.providers import provider_for, transport
from coach.providers.anthropic import AnthropicProvider
from coach.providers.base import (
    CoachProvider,
    Completion,
    EndpointNotAllowedError,
    InvalidKeyError,
    Message,
    ProviderError,
    ProviderUnavailableError,
    RateLimitedError,
    UnexpectedResponseError,
)
from coach.providers.openai_compatible import OpenAICompatibleProvider

from .fake_providers import FakeProvider, running

KEY = "sk-test-0123456789-abcdefghij"
MODEL = "llama3.1:8b"
HELLO = [Message("user", "Hello")]

ANSWER: dict[str, Any] = {
    "id": "chatcmpl-1",
    "object": "chat.completion",
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": "Hi there"},
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 12, "completion_tokens": 5, "total_tokens": 17},
}


@pytest.fixture
def base(fake: FakeProvider, settings: Any) -> str:
    """The address of the fake server as an operator would list it."""
    address = fake.url + "/v1"
    settings.AI_ALLOWED_BASE_URLS = (address,)
    return address


def provider(base: str, key: str = "", **kwargs: Any) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(base, MODEL, key, **kwargs)


def complete(fake: FakeProvider, base: str, data: object = ANSWER, status: int = 200) -> Completion:
    fake.reply(data, status)
    return provider(base, KEY).complete("", HELLO, 100)


def error_of(fake: FakeProvider, base: str, data: object, status: int = 200) -> ProviderError:
    fake.reply(data, status)
    with pytest.raises(ProviderError) as raised:
        provider(base, KEY).complete("", HELLO, 100)
    return raised.value


class TestTheRequest:
    def test_it_goes_to_chat_completions_with_a_bearer_key(
        self, fake: FakeProvider, base: str
    ) -> None:
        complete(fake, base)

        (request,) = fake.requests
        assert request["method"] == "POST"
        assert request["raw_path"] == "/v1/chat/completions"
        assert request["headers"]["authorization"] == f"Bearer {KEY}"
        assert request["headers"]["content-type"] == "application/json"
        assert request["headers"]["accept"] == "application/json"
        assert request["headers"]["user-agent"] == "PaceForge"
        assert "x-api-key" not in request["headers"]

    def test_without_a_key_no_authorization_is_sent(self, fake: FakeProvider, base: str) -> None:
        fake.reply(ANSWER)

        provider(base).complete("", HELLO, 10)

        assert "authorization" not in fake.requests[0]["headers"]

    def test_the_system_prompt_is_the_first_message(self, fake: FakeProvider, base: str) -> None:
        fake.reply(ANSWER)

        provider(base).complete(
            "You are a coach.", [Message("user", "Hi"), Message("assistant", "Hello")], 321
        )

        assert fake.requests[0]["json"] == {
            "model": MODEL,
            "max_tokens": 321,
            "messages": [
                {"role": "system", "content": "You are a coach."},
                {"role": "user", "content": "Hi"},
                {"role": "assistant", "content": "Hello"},
            ],
        }

    def test_an_empty_system_prompt_is_left_out(self, fake: FakeProvider, base: str) -> None:
        complete(fake, base)

        assert fake.requests[0]["json"]["messages"] == [{"role": "user", "content": "Hello"}]

    def test_umlauts_and_emoji_arrive_as_they_were_written(
        self, fake: FakeProvider, base: str
    ) -> None:
        fake.reply(ANSWER)

        provider(base).complete("Größe ✓", [Message("user", "Übung 🏃")], 10)

        messages = fake.requests[0]["json"]["messages"]
        assert messages[0]["content"] == "Größe ✓"
        assert messages[1]["content"] == "Übung 🏃"

    def test_the_caller_s_messages_are_not_changed(self, fake: FakeProvider, base: str) -> None:
        fake.reply(ANSWER)
        messages = [Message("user", "Hi")]

        provider(base).complete("system", messages, 10)

        assert messages == [Message("user", "Hi")]

    def test_a_provider_needs_a_model(self, base: str) -> None:
        with pytest.raises(ValueError):
            OpenAICompatibleProvider(base, "")

    def test_there_must_be_something_to_send(self, fake: FakeProvider, base: str) -> None:
        with pytest.raises(ValueError):
            provider(base).complete("", [], 10)
        assert fake.requests == []

    @pytest.mark.parametrize("limit", [0, -1])
    def test_the_answer_must_be_allowed_some_length(
        self, fake: FakeProvider, base: str, limit: int
    ) -> None:
        with pytest.raises(ValueError):
            provider(base).complete("", HELLO, limit)
        assert fake.requests == []

    def test_it_is_a_coach_provider(self, base: str) -> None:
        candidate: CoachProvider = provider(base)

        assert isinstance(candidate, CoachProvider)


class TestTheAllowList:
    def test_an_address_that_is_not_listed_is_refused_without_a_network_call(
        self, fake: FakeProvider, settings: Any
    ) -> None:
        settings.AI_ALLOWED_BASE_URLS = ("https://api.openai.com/v1",)

        with pytest.raises(EndpointNotAllowedError):
            OpenAICompatibleProvider(fake.url + "/v1", MODEL, KEY)

        assert fake.requests == []

    def test_an_empty_list_allows_nothing(self, fake: FakeProvider, settings: Any) -> None:
        settings.AI_ALLOWED_BASE_URLS = ()

        with pytest.raises(EndpointNotAllowedError):
            OpenAICompatibleProvider(fake.url + "/v1", MODEL)

    @pytest.mark.parametrize("variant", ["/", "?x=1", "/chat", "#f", " "])
    def test_only_the_listed_text_counts(self, base: str, variant: str) -> None:
        with pytest.raises(EndpointNotAllowedError):
            OpenAICompatibleProvider(base + variant, MODEL)

    def test_the_address_of_the_fake_is_taken_from_the_list_not_from_the_request(
        self, fake: FakeProvider, base: str
    ) -> None:
        complete(fake, base)

        assert fake.requests[0]["raw_path"].startswith("/v1/")

    def test_the_refusal_says_nothing_about_the_address_or_the_key(self, settings: Any) -> None:
        settings.AI_ALLOWED_BASE_URLS = ()

        with pytest.raises(EndpointNotAllowedError) as raised:
            OpenAICompatibleProvider("http://169.254.169.254/latest", MODEL, KEY)

        assert "169.254" not in str(raised.value)
        assert KEY not in str(raised.value)

    def test_the_text_of_the_provider_does_not_show_the_key(self, base: str) -> None:
        text = repr(provider(base, KEY))

        assert KEY not in text
        assert MODEL in text


class TestTheAnswer:
    def test_the_text_and_the_tokens_are_taken_over(self, fake: FakeProvider, base: str) -> None:
        assert complete(fake, base) == Completion("Hi there", 12, 5, False)

    def test_only_the_first_choice_counts(self, fake: FakeProvider, base: str) -> None:
        second = {"message": {"role": "assistant", "content": "Second"}, "finish_reason": "stop"}
        data = {**ANSWER, "choices": [*ANSWER["choices"], second]}

        assert complete(fake, base, data).text == "Hi there"

    def test_a_cut_off_answer_says_so(self, fake: FakeProvider, base: str) -> None:
        choice = {**ANSWER["choices"][0], "finish_reason": "length"}

        assert complete(fake, base, {**ANSWER, "choices": [choice]}).truncated is True

    @pytest.mark.parametrize("reason", ["stop", "tool_calls", "content_filter", None, 5, "LENGTH"])
    def test_other_reasons_are_not_a_cut_off(
        self, fake: FakeProvider, base: str, reason: object
    ) -> None:
        choice = {**ANSWER["choices"][0], "finish_reason": reason}

        assert complete(fake, base, {**ANSWER, "choices": [choice]}).truncated is False

    def test_missing_usage_gives_no_counts(self, fake: FakeProvider, base: str) -> None:
        data = {k: v for k, v in ANSWER.items() if k != "usage"}

        assert complete(fake, base, data) == Completion("Hi there", None, None, False)

    @pytest.mark.parametrize(
        ("usage", "expected"),
        [
            ({"prompt_tokens": 7}, (7, None)),
            ({"completion_tokens": 7}, (None, 7)),
            ({"prompt_tokens": 0, "completion_tokens": 0}, (0, 0)),
            ({"prompt_tokens": "12", "completion_tokens": 5}, (None, 5)),
            ({"prompt_tokens": 1.5, "completion_tokens": 5}, (None, 5)),
            ({"prompt_tokens": -1, "completion_tokens": True}, (None, None)),
            ({"prompt_tokens": None, "completion_tokens": None}, (None, None)),
            ({"input_tokens": 3, "output_tokens": 4}, (None, None)),
            ([], (None, None)),
            ("many", (None, None)),
        ],
    )
    def test_counts_that_make_no_sense_are_dropped_one_by_one(
        self,
        fake: FakeProvider,
        base: str,
        usage: object,
        expected: tuple[int | None, int | None],
    ) -> None:
        result = complete(fake, base, {**ANSWER, "usage": usage})

        assert (result.input_tokens, result.output_tokens) == expected
        assert result.text == "Hi there"

    @pytest.mark.parametrize(
        "data",
        [
            [],
            "text",
            5,
            None,
            {},
            {"choices": None},
            {"choices": "Hi"},
            {"choices": {}},
            {"choices": {"0": {"message": {"content": "Hi"}}}},
            {"choices": {"a": 1}},
            {"choices": "Hi there"},
            {"choices": []},
            {"choices": [None]},
            {"choices": ["Hi"]},
            {"choices": [{}]},
            {"choices": [{"message": None}]},
            {"choices": [{"message": "Hi"}]},
            {"choices": [{"message": {}}]},
            {"choices": [{"message": {"content": None}}]},
            {"choices": [{"message": {"content": ""}}]},
            {"choices": [{"message": {"content": 5}}]},
            {"choices": [{"message": {"content": ["Hi"]}}]},
            {"choices": [{"text": "Hi"}]},
        ],
    )
    def test_an_answer_of_the_wrong_shape_is_rejected(
        self, fake: FakeProvider, base: str, data: object
    ) -> None:
        assert isinstance(error_of(fake, base, data), UnexpectedResponseError)

    def test_an_answer_that_is_not_json_is_rejected(self, fake: FakeProvider, base: str) -> None:
        fake.body = b"<html>oops</html>"

        with pytest.raises(UnexpectedResponseError):
            provider(base).complete("", HELLO, 10)

    def test_an_answer_that_is_too_large_is_rejected(
        self, fake: FakeProvider, base: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(transport, "MAX_RESPONSE_BYTES", 200)
        fake.reply({"choices": [{"message": {"content": "x" * 500}, "finish_reason": "stop"}]})

        with pytest.raises(UnexpectedResponseError, match="larger"):
            provider(base).complete("", HELLO, 10)

    def test_an_answer_that_is_cut_off_is_a_failure_to_reach_the_provider(
        self, fake: FakeProvider, base: str
    ) -> None:
        fake.reply(ANSWER)
        fake.missing_bytes = 50

        with pytest.raises(ProviderUnavailableError):
            provider(base).complete("", HELLO, 10)


class TestFailures:
    @pytest.mark.parametrize("status", [401, 403])
    def test_a_refused_key(self, fake: FakeProvider, base: str, status: int) -> None:
        assert isinstance(error_of(fake, base, {"error": {}}, status), InvalidKeyError)

    @pytest.mark.parametrize("status", [408, 500, 502, 503, 504])
    def test_a_provider_that_is_busy_or_broken(
        self, fake: FakeProvider, base: str, status: int
    ) -> None:
        assert isinstance(error_of(fake, base, {}, status), ProviderUnavailableError)

    @pytest.mark.parametrize("status", [400, 404, 422, 301, 307])
    def test_other_statuses_are_unexpected_and_say_which(
        self, fake: FakeProvider, base: str, status: int
    ) -> None:
        error = error_of(fake, base, {}, status)

        assert isinstance(error, UnexpectedResponseError)
        assert f"HTTP {status}" in str(error)

    def test_a_busy_provider_says_how_long_to_wait(self, fake: FakeProvider, base: str) -> None:
        fake.headers = {"Retry-After": "30"}

        error = error_of(fake, base, {}, 429)

        assert isinstance(error, RateLimitedError)
        assert error.retry_after == 30

    def test_a_redirect_is_not_followed(self, fake: FakeProvider, base: str) -> None:
        error = error_of(fake, base, {}, 302)

        assert isinstance(error, UnexpectedResponseError)
        assert [r["raw_path"] for r in fake.requests] == ["/v1/chat/completions"]

    def test_a_provider_that_cannot_be_reached(self, settings: Any) -> None:
        with running() as gone:
            address = gone.url + "/v1"
        settings.AI_ALLOWED_BASE_URLS = (address,)

        with pytest.raises(ProviderUnavailableError):
            OpenAICompatibleProvider(address, MODEL, KEY).complete("", HELLO, 10)

    def test_a_provider_that_takes_too_long(self, fake: FakeProvider, base: str) -> None:
        fake.reply(ANSWER)
        fake.delay = 1.0

        with pytest.raises(ProviderUnavailableError):
            provider(base, KEY, timeout=0.2).complete("", HELLO, 10)


class TestSecrecy:
    """The key must not turn up anywhere a person or a log could see it."""

    @pytest.mark.parametrize(
        ("status", "data"),
        [
            (401, {"error": {"message": f"Incorrect API key provided: {KEY}"}}),
            (429, {"error": {"message": "slow down, my prompt was Hello"}}),
            (500, {"error": {"message": "boom Hello"}}),
            (400, {"error": {"message": f"bad request for {KEY}: Hello"}}),
            (200, {"choices": [{"message": {"content": None}}], "echo": "Hello"}),
        ],
    )
    def test_errors_and_their_tracebacks_carry_neither_key_prompt_nor_provider_text(
        self,
        fake: FakeProvider,
        base: str,
        caplog: pytest.LogCaptureFixture,
        status: int,
        data: object,
    ) -> None:
        caplog.set_level(logging.DEBUG)
        fake.reply(data, status)

        with pytest.raises(ProviderError) as raised:
            provider(base, KEY).complete("", HELLO, 10)

        everything = "".join(traceback.format_exception(raised.value)) + str(raised.value)
        everything += repr(raised.value) + caplog.text
        assert KEY not in everything
        assert "bearer" not in everything.lower()
        assert "Hello" not in everything
        assert "slow down" not in everything
        assert raised.value.__cause__ is None
        assert raised.value.__context__ is None or raised.value.__suppress_context__

    def test_an_unreachable_provider_does_not_leak_the_key_either(
        self, caplog: pytest.LogCaptureFixture, settings: Any
    ) -> None:
        caplog.set_level(logging.DEBUG)
        with running() as gone:
            address = gone.url + "/v1"
        settings.AI_ALLOWED_BASE_URLS = (address,)

        with pytest.raises(ProviderError) as raised:
            OpenAICompatibleProvider(address, MODEL, KEY).complete("", HELLO, 10)

        everything = "".join(traceback.format_exception(raised.value)) + caplog.text
        assert KEY not in everything
        assert raised.value.__cause__ is None
        assert raised.value.__suppress_context__


@pytest.mark.django_db
class TestChoosingTheAdapter:
    @pytest.fixture
    def alice(self) -> User:
        return User.objects.create_user("alice@example.com")

    def test_anthropic_gets_the_anthropic_adapter(self, fake: FakeProvider, alice: User) -> None:
        config = AIProviderConfiguration.objects.create(
            owner=alice, provider="anthropic", model="claude-sonnet-5-5", api_key=KEY
        )
        fake.reply({"content": [{"type": "text", "text": "Hi"}], "usage": {"input_tokens": 1}})

        chosen = provider_for(config)
        result = chosen.complete("", HELLO, 10)

        assert isinstance(chosen, AnthropicProvider)
        assert result.text == "Hi"
        assert fake.requests[0]["raw_path"] == "/v1/messages"
        assert fake.requests[0]["headers"]["x-api-key"] == KEY
        assert fake.requests[0]["json"]["model"] == "claude-sonnet-5-5"

    def test_a_compatible_endpoint_gets_the_compatible_adapter(
        self, fake: FakeProvider, base: str, alice: User
    ) -> None:
        config = AIProviderConfiguration.objects.create(
            owner=alice, provider="openai_compatible", model=MODEL, api_key=KEY, base_url=base
        )
        fake.reply(ANSWER)

        chosen = provider_for(config)
        result = chosen.complete("", HELLO, 10)

        assert isinstance(chosen, OpenAICompatibleProvider)
        assert result.text == "Hi there"
        assert fake.requests[0]["raw_path"] == "/v1/chat/completions"
        assert fake.requests[0]["headers"]["authorization"] == f"Bearer {KEY}"
        assert fake.requests[0]["json"]["model"] == MODEL

    def test_a_local_endpoint_without_a_key_sends_none(
        self, fake: FakeProvider, base: str, alice: User
    ) -> None:
        config = AIProviderConfiguration.objects.create(
            owner=alice, provider="openai_compatible", model=MODEL, api_key="", base_url=base
        )
        fake.reply(ANSWER)

        provider_for(config).complete("", HELLO, 10)

        assert "authorization" not in fake.requests[0]["headers"]

    def test_an_address_the_operator_has_removed_is_refused_before_any_call(
        self, fake: FakeProvider, base: str, alice: User, settings: Any
    ) -> None:
        config = AIProviderConfiguration.objects.create(
            owner=alice, provider="openai_compatible", model=MODEL, api_key=KEY, base_url=base
        )
        settings.AI_ALLOWED_BASE_URLS = ()

        with pytest.raises(EndpointNotAllowedError):
            provider_for(config)

        assert fake.requests == []

    def test_an_unknown_provider_is_refused(self, alice: User) -> None:
        config = AIProviderConfiguration(owner=alice, provider="gemini", model="x", api_key=KEY)

        with pytest.raises(ValueError):
            provider_for(config)

    def test_the_answer_is_json_that_can_be_parsed_back(
        self, fake: FakeProvider, base: str, alice: User
    ) -> None:
        # A structured answer (the weekly plan will be one) comes back as the exact text.
        payload = json.dumps({"days": [{"minutes": 60}]})
        config = AIProviderConfiguration.objects.create(
            owner=alice, provider="openai_compatible", model=MODEL, api_key="", base_url=base
        )
        fake.reply({"choices": [{"message": {"content": payload}, "finish_reason": "stop"}]})

        text = provider_for(config).complete("", HELLO, 10).text

        assert json.loads(text) == {"days": [{"minutes": 60}]}
