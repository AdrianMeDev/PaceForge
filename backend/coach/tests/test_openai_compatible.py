import json
import logging
import traceback
from typing import Any

import pytest

from accounts.models import User
from coach.models import AIProviderConfiguration
from coach.providers import openai_compatible, provider_for, transport
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
from coach.providers.openai_compatible import JSON_MODE_HOSTS, OpenAICompatibleProvider

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


class TestJsonOutput:
    """``response_format`` goes only to hosts known to take it, and only when it is asked for."""

    JSON_MODE = {"response_format": {"type": "json_object"}}

    @pytest.fixture
    def sent(self, monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
        bodies: list[dict[str, Any]] = []

        def record(url: str, headers: dict[str, str], payload: dict[str, Any], **_: Any) -> Any:
            bodies.append(payload)
            return ANSWER

        monkeypatch.setattr(openai_compatible, "post_json", record)
        return bodies

    def ask(self, settings: Any, address: str, json_output: bool | None) -> None:
        settings.AI_ALLOWED_BASE_URLS = (address,)
        kwargs: dict[str, Any] = {} if json_output is None else {"json_output": json_output}
        OpenAICompatibleProvider(address, MODEL, KEY).complete("", HELLO, 10, **kwargs)

    def test_the_known_host_is_deepseek_and_only_deepseek(self) -> None:
        assert JSON_MODE_HOSTS == {"api.deepseek.com"}

    @pytest.mark.parametrize(
        "address",
        [
            "https://api.deepseek.com",
            "https://api.deepseek.com/v1",
            "http://api.deepseek.com:8443/v1",
        ],
    )
    def test_a_known_host_gets_json_mode_when_it_is_asked_for(
        self, settings: Any, sent: list[dict[str, Any]], address: str
    ) -> None:
        self.ask(settings, address, True)

        assert sent[0]["response_format"] == {"type": "json_object"}
        assert sent[0]["messages"] == [{"role": "user", "content": "Hello"}]

    @pytest.mark.parametrize("json_output", [False, None])
    def test_a_known_host_gets_nothing_extra_when_it_is_not_asked_for(
        self, settings: Any, sent: list[dict[str, Any]], json_output: bool | None
    ) -> None:
        self.ask(settings, "https://api.deepseek.com", json_output)

        assert "response_format" not in sent[0]

    @pytest.mark.parametrize(
        "address",
        [
            "https://openrouter.ai/api/v1",
            "https://api.openai.com/v1",
            "http://localhost:11434/v1",
            "https://api.deepseek.com.evil.example/v1",
            "https://evil.example/api.deepseek.com",
            "https://deepseek.com",
        ],
    )
    def test_any_other_host_never_gets_it(
        self, settings: Any, sent: list[dict[str, Any]], address: str
    ) -> None:
        self.ask(settings, address, True)

        assert "response_format" not in sent[0]

    def test_the_rest_of_the_request_is_the_same(
        self, settings: Any, sent: list[dict[str, Any]]
    ) -> None:
        self.ask(settings, "https://api.deepseek.com", False)
        self.ask(settings, "https://api.deepseek.com", True)

        assert {**sent[0], **self.JSON_MODE} == sent[1]

    def test_it_travels_over_a_real_connection_to_a_listed_host(
        self, fake: FakeProvider, base: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(openai_compatible, "JSON_MODE_HOSTS", frozenset({"127.0.0.1"}))
        fake.reply(ANSWER)

        provider(base, KEY).complete("", HELLO, 10, json_output=True)

        assert fake.requests[0]["json"]["response_format"] == {"type": "json_object"}


class TestAllowedAddress:
    def test_allowlist_is_checked_again_before_the_call(
        self, settings: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        address = "https://example.org/v1"
        settings.AI_ALLOWED_BASE_URLS = (address,)
        chosen = provider(address)
        settings.AI_ALLOWED_BASE_URLS = ()

        def unexpected_call(*args: object, **kwargs: object) -> object:
            pytest.fail("A removed endpoint must not receive a request.")

        monkeypatch.setattr(openai_compatible, "post_json", unexpected_call)
        with pytest.raises(
            EndpointNotAllowedError, match="This address is not allowed on this server."
        ):
            chosen.complete("", HELLO, 10)

    @pytest.mark.parametrize(
        "address", ["ftp://example.org", "https://example.org/", "https://example.org/a\nb"]
    )
    def test_invalid_allowlist_override_is_refused(self, settings: Any, address: str) -> None:
        settings.AI_ALLOWED_BASE_URLS = (address,)
        with pytest.raises(EndpointNotAllowedError):
            provider(address)


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

        assert fake.requests == []

    @pytest.mark.parametrize("variant", ["/", "?x=1", "/chat", "#f", " "])
    def test_only_the_listed_text_counts(self, fake: FakeProvider, base: str, variant: str) -> None:
        with pytest.raises(EndpointNotAllowedError):
            OpenAICompatibleProvider(base + variant, MODEL)

        assert fake.requests == []

    def test_only_an_approved_self_hosted_endpoint_receives_requests(self, settings: Any) -> None:
        with running() as approved, running() as unlisted:
            approved_url = approved.url + "/v1"
            unlisted_url = unlisted.url + "/v1"
            settings.AI_ALLOWED_BASE_URLS = (approved_url,)
            approved.reply(ANSWER)

            result = provider(approved_url, KEY).complete("", HELLO, 100)

            assert result == Completion("Hi there", 12, 5, False)
            assert len(approved.requests) == 1
            assert approved.requests[0]["raw_path"] == "/v1/chat/completions"
            assert unlisted.requests == []

            with pytest.raises(EndpointNotAllowedError):
                provider(unlisted_url, KEY)

            assert len(approved.requests) == 1
            assert unlisted.requests == []

    def test_removing_an_endpoint_before_complete_makes_zero_requests(
        self, fake: FakeProvider, base: str, settings: Any
    ) -> None:
        fake.reply(ANSWER)
        chosen = provider(base, KEY)
        settings.AI_ALLOWED_BASE_URLS = ()

        with pytest.raises(
            EndpointNotAllowedError, match="This address is not allowed on this server."
        ):
            chosen.complete("", HELLO, 100)

        assert fake.requests == []

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

    @pytest.mark.parametrize(
        ("details", "expected"),
        [
            ({"cached_tokens": 1024}, 1024),
            ({"cached_tokens": 0}, 0),
            ({"cached_tokens": "1024"}, None),
            ({"cached_tokens": -1}, None),
            ({"cached_tokens": 1.5}, None),
            ({"cached_tokens": True}, None),
            ({"audio_tokens": 3}, None),
            ({}, None),
            (None, None),
            ("many", None),
        ],
    )
    def test_the_cached_part_of_the_prompt_is_read_where_it_is_given(
        self, fake: FakeProvider, base: str, details: object, expected: int | None
    ) -> None:
        usage = {"prompt_tokens": 2000, "completion_tokens": 5, "prompt_tokens_details": details}

        result = complete(fake, base, {**ANSWER, "usage": usage})

        assert result.cache_read_tokens == expected
        assert result.cache_write_tokens is None
        assert result.input_tokens == 2000

    def test_without_the_details_there_is_no_cache_count(
        self, fake: FakeProvider, base: str
    ) -> None:
        assert complete(fake, base).cache_read_tokens is None

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

    @pytest.mark.parametrize(
        "raw_body",
        [
            b'{"choices": [{"message": {"content": "Hi"}}], "usage": {"prompt_tokens": NaN}}',
            b'{"choices": [{"message": {"content": "Hi"}}], "usage": {"prompt_tokens": Infinity}}',
            b'{"choices": [{"message": {"content": "Hi"}}], "usage": {"prompt_tokens": -Infinity}}',
            b'{"choices": [{"message": {"content": "Hi"}}], "usage": {"nested": [1e400]}}',
        ],
        ids=["nan", "infinity", "neg-infinity", "nested-overflow"],
    )
    def test_an_answer_with_non_finite_numbers_is_rejected(
        self, fake: FakeProvider, base: str, raw_body: bytes
    ) -> None:
        fake.body = raw_body

        with pytest.raises(UnexpectedResponseError) as raised:
            provider(base).complete("", HELLO, 10)

        assert str(raised.value) == "The answer is not JSON."

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

    @pytest.mark.parametrize(
        "bad_key",
        [
            "sk-bad\nX-Injected: 1",
            "sk-bad\rX-Injected: 1",
            "sk-bad\x00key",
            "sk-bad-🔑",
            "sk-bad-ä",
        ],
        ids=["newline", "carriage-return", "nul", "emoji", "non-ascii"],
    )
    def test_invalid_api_key_characters_are_rejected_without_leaking_or_sending(
        self,
        fake: FakeProvider,
        base: str,
        caplog: pytest.LogCaptureFixture,
        bad_key: str,
    ) -> None:
        caplog.set_level(logging.DEBUG)
        fake.reply(ANSWER)

        with pytest.raises(ProviderError) as raised:
            provider(base, bad_key).complete("", HELLO, 10)

        assert type(raised.value) is ProviderError
        assert fake.requests == []
        everything = "".join(traceback.format_exception(raised.value)) + str(raised.value)
        everything += repr(raised.value) + caplog.text
        assert bad_key not in everything
        assert "sk-bad" not in everything
        assert "bearer" not in everything.lower()
        assert raised.value.__cause__ is None
        assert raised.value.__context__ is None or raised.value.__suppress_context__

    @pytest.mark.parametrize(
        ("headers", "secret"),
        [
            ({"": "secret-val"}, "secret-val"),
            ({"Bad Name": "secret-val"}, "Bad Name"),
            ({"Bad:Name": "secret-val"}, "Bad:Name"),
            ({"Bad\nName": "secret-val"}, "Bad\nName"),
            ({"Bad-ä": "secret-val"}, "Bad-ä"),
            ({"X-Api-Key": "secret\nval"}, "secret\nval"),
            ({"X-Api-Key": "secret\rval"}, "secret\rval"),
            ({"X-Api-Key": "secret\x00val"}, "secret\x00val"),
            ({"X-Api-Key": "secret\x7fval"}, "secret\x7fval"),
            ({"X-Api-Key": "secret-ä"}, "secret-ä"),
        ],
        ids=[
            "empty-name",
            "space-in-name",
            "colon-in-name",
            "newline-in-name",
            "non-ascii-name",
            "newline-in-value",
            "cr-in-value",
            "nul-in-value",
            "del-in-value",
            "non-ascii-value",
        ],
    )
    def test_post_json_rejects_invalid_headers_without_leaking_or_sending(
        self,
        fake: FakeProvider,
        caplog: pytest.LogCaptureFixture,
        headers: dict[str, str],
        secret: str,
    ) -> None:
        caplog.set_level(logging.DEBUG)
        fake.reply(ANSWER)

        with pytest.raises(ProviderError) as raised:
            transport.post_json(fake.url + "/v1/chat/completions", headers, {"ok": True})

        assert type(raised.value) is ProviderError
        assert fake.requests == []
        everything = "".join(traceback.format_exception(raised.value)) + str(raised.value)
        everything += repr(raised.value) + caplog.text
        assert secret not in everything
        assert "x-api-key" not in everything.lower()
        assert raised.value.__cause__ is None
        assert raised.value.__context__ is None or raised.value.__suppress_context__

    @pytest.mark.parametrize(
        "headers",
        [
            {"X-Api-Key\nInjected": "secret-val"},
            {"X-Api-Key": "secret\nval"},
            {"X-Api-Key": "secret-ä"},
        ],
        ids=["bad-name", "bad-value", "non-ascii-value"],
    )
    def test_a_rejected_header_does_not_chain_a_pending_error_into_the_traceback(
        self,
        fake: FakeProvider,
        caplog: pytest.LogCaptureFixture,
        headers: dict[str, str],
    ) -> None:
        caplog.set_level(logging.DEBUG)
        fake.reply(ANSWER)

        # The caller is already handling an error that names the key; the fixed message must
        # not drag that error (and the key in it) into the traceback.
        try:
            raise ValueError(f"bad header value {KEY}")
        except ValueError:
            with pytest.raises(ProviderError) as raised:
                transport.post_json(fake.url + "/v1/chat/completions", headers, {"ok": True})

        assert type(raised.value) is ProviderError
        assert fake.requests == []
        assert raised.value.__cause__ is None
        assert raised.value.__suppress_context__
        everything = "".join(traceback.format_exception(raised.value)) + str(raised.value)
        everything += repr(raised.value) + caplog.text
        assert KEY not in everything
        assert "secret" not in everything
        assert "bad header value" not in everything

    def test_post_json_wraps_value_error_from_request_or_open_without_leaking(
        self,
        fake: FakeProvider,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        caplog.set_level(logging.DEBUG)

        def fail_open(*args: object, **kwargs: object) -> object:
            raise ValueError(f"bad header value {KEY}")

        monkeypatch.setattr(transport._opener, "open", fail_open)

        with pytest.raises(ProviderError) as raised:
            transport.post_json(fake.url, {"Authorization": f"Bearer {KEY}"}, {"ok": True})

        assert type(raised.value) is ProviderError
        assert fake.requests == []
        everything = "".join(traceback.format_exception(raised.value)) + str(raised.value)
        everything += repr(raised.value) + caplog.text
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
