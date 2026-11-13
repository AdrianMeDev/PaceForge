import json
import logging
import traceback
from typing import Any

import pytest

from coach.providers import transport
from coach.providers.anthropic import API_VERSION, AnthropicProvider
from coach.providers.base import (
    CoachProvider,
    Completion,
    InvalidKeyError,
    Message,
    ProviderError,
    ProviderUnavailableError,
    RateLimitedError,
    UnexpectedResponseError,
)

from .fake_providers import FakeProvider, running

KEY = "sk-ant-test-0123456789-abcdefghij"
MODEL = "claude-sonnet-5-5"
HELLO = [Message("user", "Hello")]

ANSWER = {
    "id": "msg_01",
    "type": "message",
    "role": "assistant",
    "content": [{"type": "text", "text": "Hi there"}],
    "stop_reason": "end_turn",
    "usage": {"input_tokens": 12, "output_tokens": 5},
}


def provider(fake: FakeProvider, **kwargs: Any) -> AnthropicProvider:
    return AnthropicProvider(KEY, MODEL, base_url=fake.url, **kwargs)


def complete(fake: FakeProvider, data: object = ANSWER, status: int = 200) -> Completion:
    fake.reply(data, status)
    return provider(fake).complete("", HELLO, 100)


def error_of(fake: FakeProvider, data: object, status: int = 200) -> ProviderError:
    fake.reply(data, status)
    with pytest.raises(ProviderError) as raised:
        provider(fake).complete("", HELLO, 100)
    return raised.value


class TestTheRequest:
    def test_it_goes_to_the_messages_endpoint_with_the_key_and_the_version(
        self, fake: FakeProvider
    ) -> None:
        complete(fake)

        (request,) = fake.requests
        assert request["method"] == "POST"
        assert request["path"] == "/v1/messages"
        assert request["raw_path"] == "/v1/messages"
        assert request["headers"]["accept"] == "application/json"
        assert request["headers"]["x-api-key"] == KEY
        assert request["headers"]["anthropic-version"] == API_VERSION == "2023-06-01"
        assert request["headers"]["content-type"] == "application/json"
        assert request["headers"]["user-agent"] == "PaceForge"
        assert "authorization" not in request["headers"]

    def test_the_body_has_model_limit_system_and_messages(self, fake: FakeProvider) -> None:
        fake.reply(ANSWER)

        provider(fake).complete(
            "You are a coach.", [Message("user", "Hi"), Message("assistant", "Hello")], 321
        )

        assert fake.requests[0]["json"] == {
            "model": MODEL,
            "max_tokens": 321,
            "system": "You are a coach.",
            "messages": [
                {"role": "user", "content": "Hi"},
                {"role": "assistant", "content": "Hello"},
            ],
        }

    def test_an_empty_system_prompt_is_left_out(self, fake: FakeProvider) -> None:
        complete(fake)

        assert "system" not in fake.requests[0]["json"]

    def test_umlauts_and_emoji_arrive_as_they_were_written(self, fake: FakeProvider) -> None:
        fake.reply(ANSWER)

        provider(fake).complete("Größe ✓", [Message("user", "Übung 🏃 für Ältere")], 10)

        body = fake.requests[0]["json"]
        assert body["system"] == "Größe ✓"
        assert body["messages"][0]["content"] == "Übung 🏃 für Ältere"

    def test_the_address_comes_from_the_settings_and_a_trailing_slash_does_not_matter(
        self, fake: FakeProvider, settings: Any
    ) -> None:
        settings.ANTHROPIC_API_BASE_URL = fake.url + "/"
        fake.reply(ANSWER)

        AnthropicProvider(KEY, MODEL).complete("", HELLO, 10)

        assert fake.requests[0]["raw_path"] == "/v1/messages"

    def test_an_address_given_explicitly_wins(self, fake: FakeProvider, settings: Any) -> None:
        settings.ANTHROPIC_API_BASE_URL = "http://127.0.0.1:1"
        fake.reply(ANSWER)

        AnthropicProvider(KEY, MODEL, base_url=fake.url + "/").complete("", HELLO, 10)

        assert [r["raw_path"] for r in fake.requests] == ["/v1/messages"]

    @pytest.mark.parametrize(("key", "model"), [("", MODEL), (KEY, "")], ids=["no key", "no model"])
    def test_a_provider_needs_a_key_and_a_model(self, key: str, model: str) -> None:
        with pytest.raises(ValueError):
            AnthropicProvider(key, model, base_url="http://127.0.0.1:1")

    def test_there_must_be_something_to_send(self, fake: FakeProvider) -> None:
        with pytest.raises(ValueError):
            provider(fake).complete("", [], 10)
        assert fake.requests == []

    @pytest.mark.parametrize("limit", [0, -1])
    def test_the_answer_must_be_allowed_some_length(self, fake: FakeProvider, limit: int) -> None:
        with pytest.raises(ValueError):
            provider(fake).complete("", HELLO, limit)
        assert fake.requests == []

    def test_it_is_a_coach_provider(self, fake: FakeProvider) -> None:
        candidate: CoachProvider = provider(fake)

        assert isinstance(candidate, CoachProvider)


class TestTheAnswer:
    def test_the_text_and_the_tokens_are_taken_over(self, fake: FakeProvider) -> None:
        assert complete(fake) == Completion("Hi there", 12, 5, False)

    def test_several_text_blocks_are_joined_and_other_blocks_are_ignored(
        self, fake: FakeProvider
    ) -> None:
        content = [
            {"type": "thinking", "thinking": "hmm", "text": "NOT THIS"},
            {"type": "text", "text": "One "},
            {"type": "tool_use", "id": "t", "name": "x", "input": {}},
            {"type": "text", "text": "two"},
            "not a block",
            {"type": "text"},
            {"type": "text", "text": 5},
        ]

        result = complete(fake, {**ANSWER, "content": content})

        assert result.text == "One two"

    def test_a_cut_off_answer_says_so(self, fake: FakeProvider) -> None:
        assert complete(fake, {**ANSWER, "stop_reason": "max_tokens"}).truncated is True

    @pytest.mark.parametrize("reason", ["end_turn", "stop_sequence", None, 5, "MAX_TOKENS"])
    def test_other_reasons_are_not_a_cut_off(self, fake: FakeProvider, reason: object) -> None:
        assert complete(fake, {**ANSWER, "stop_reason": reason}).truncated is False

    def test_missing_usage_gives_no_counts(self, fake: FakeProvider) -> None:
        data = {k: v for k, v in ANSWER.items() if k != "usage"}

        assert complete(fake, data) == Completion("Hi there", None, None, False)

    @pytest.mark.parametrize(
        ("usage", "expected"),
        [
            ({"input_tokens": 7}, (7, None)),
            ({"output_tokens": 7}, (None, 7)),
            ({"input_tokens": 0, "output_tokens": 0}, (0, 0)),
            ({"input_tokens": "12", "output_tokens": 5}, (None, 5)),
            ({"input_tokens": 1.5, "output_tokens": 5}, (None, 5)),
            ({"input_tokens": -1, "output_tokens": True}, (None, None)),
            ({"input_tokens": None, "output_tokens": None}, (None, None)),
            ([], (None, None)),
            ("many", (None, None)),
        ],
    )
    def test_counts_that_make_no_sense_are_dropped_one_by_one(
        self, fake: FakeProvider, usage: object, expected: tuple[int | None, int | None]
    ) -> None:
        result = complete(fake, {**ANSWER, "usage": usage})

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
            {"content": None},
            {"content": "Hi there"},
            {"content": {"type": "text", "text": "Hi"}},
            {"content": []},
            {"content": [{"type": "tool_use", "id": "t"}]},
            {"content": [{"type": "text", "text": ""}]},
            {"content": [{"type": "text", "text": 5}]},
            {"content": ["Hi there"]},
        ],
    )
    def test_an_answer_of_the_wrong_shape_is_rejected(
        self, fake: FakeProvider, data: object
    ) -> None:
        assert isinstance(error_of(fake, data), UnexpectedResponseError)

    def test_an_answer_that_is_not_json_is_rejected(self, fake: FakeProvider) -> None:
        fake.body = b"<html>oops</html>"

        with pytest.raises(UnexpectedResponseError):
            provider(fake).complete("", HELLO, 10)

    def test_an_answer_that_is_too_large_is_rejected(
        self, fake: FakeProvider, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(transport, "MAX_RESPONSE_BYTES", 200)
        fake.reply({**ANSWER, "content": [{"type": "text", "text": "x" * 500}]})

        with pytest.raises(UnexpectedResponseError, match="larger"):
            provider(fake).complete("", HELLO, 10)

    def test_an_answer_of_exactly_the_limit_is_accepted(
        self, fake: FakeProvider, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake.reply(ANSWER)
        monkeypatch.setattr(transport, "MAX_RESPONSE_BYTES", len(fake.body))

        assert provider(fake).complete("", HELLO, 10).text == "Hi there"

    def test_an_answer_that_is_cut_off_is_a_failure_to_reach_the_provider(
        self, fake: FakeProvider
    ) -> None:
        fake.reply(ANSWER)
        fake.missing_bytes = 50

        with pytest.raises(ProviderUnavailableError):
            provider(fake).complete("", HELLO, 10)


class TestFailures:
    @pytest.mark.parametrize("status", [401, 403])
    def test_a_refused_key(self, fake: FakeProvider, status: int) -> None:
        error = error_of(fake, {"error": {"type": "authentication_error"}}, status)

        assert isinstance(error, InvalidKeyError)

    @pytest.mark.parametrize("status", [408, 500, 502, 503, 504, 529])
    def test_a_provider_that_is_busy_or_broken(self, fake: FakeProvider, status: int) -> None:
        assert isinstance(error_of(fake, {}, status), ProviderUnavailableError)

    @pytest.mark.parametrize("status", [400, 402, 404, 413, 422, 418, 301, 307])
    def test_other_statuses_are_unexpected_and_say_which(
        self, fake: FakeProvider, status: int
    ) -> None:
        error = error_of(fake, {}, status)

        assert isinstance(error, UnexpectedResponseError)
        assert f"HTTP {status}" in str(error)

    @pytest.mark.parametrize("status", [201, 204, 206])
    def test_a_success_that_is_not_a_200_is_unexpected(
        self, fake: FakeProvider, status: int
    ) -> None:
        assert isinstance(error_of(fake, ANSWER, status), UnexpectedResponseError)

    @pytest.mark.parametrize(
        ("header", "expected"),
        [
            ("30", 30),
            (" 30 ", 30),
            ("0", 0),
            ("3600", 3600),
            ("99999", 3600),
            ("3601", 3600),
            ("-5", None),
            ("1.5", None),
            ("abc", None),
            ("", None),
            ("Wed, 21 Oct 2026 07:28:00 GMT", None),
            ("1" * 20, None),
        ],
    )
    def test_the_wait_a_busy_provider_asks_for(
        self, fake: FakeProvider, header: str, expected: int | None
    ) -> None:
        fake.headers = {"Retry-After": header}

        error = error_of(fake, {}, 429)

        assert isinstance(error, RateLimitedError)
        assert error.retry_after == expected

    @pytest.mark.parametrize("header", ["١٢", "²", "１２", "1_000", "0x10", "1e3", "+5", "5 5"])
    def test_a_wait_that_is_not_plain_ascii_digits_is_ignored(self, header: str) -> None:
        error = transport.error_for_status(429, header)

        assert isinstance(error, RateLimitedError)
        assert error.retry_after is None

    def test_a_busy_provider_without_a_wait(self, fake: FakeProvider) -> None:
        error = error_of(fake, {}, 429)

        assert isinstance(error, RateLimitedError)
        assert error.retry_after is None

    def test_a_redirect_is_not_followed(self, fake: FakeProvider) -> None:
        error = error_of(fake, {}, 302)

        assert isinstance(error, UnexpectedResponseError)
        assert [r["path"] for r in fake.requests] == ["/v1/messages"]

    def test_a_provider_that_cannot_be_reached(self) -> None:
        with running() as gone:
            address = gone.url
        with pytest.raises(ProviderUnavailableError):
            AnthropicProvider(KEY, MODEL, base_url=address).complete("", HELLO, 10)

    def test_a_provider_that_takes_too_long(self, fake: FakeProvider) -> None:
        fake.reply(ANSWER)
        fake.delay = 1.0

        with pytest.raises(ProviderUnavailableError):
            provider(fake, timeout=0.2).complete("", HELLO, 10)


class TestReadingTheAnswer:
    def test_at_most_the_limit_plus_one_byte_is_read(self, monkeypatch: pytest.MonkeyPatch) -> None:
        asked: list[int | None] = []

        class Answer:
            status = 200
            length = None

            def __enter__(self) -> Answer:
                return self

            def __exit__(self, *args: object) -> None:
                return None

            def read(self, amount: int | None = None) -> bytes:
                asked.append(amount)
                return json.dumps(ANSWER).encode()

        monkeypatch.setattr(transport._opener, "open", lambda *a, **k: Answer())

        AnthropicProvider(KEY, MODEL, base_url="http://127.0.0.1:1").complete("", HELLO, 10)

        assert asked == [transport.MAX_RESPONSE_BYTES + 1]


class TestSecrecy:
    """The key must not turn up anywhere a person or a log could see it."""

    def test_the_text_of_the_provider_does_not_show_the_key(self, fake: FakeProvider) -> None:
        text = repr(provider(fake))

        assert KEY not in text
        assert MODEL in text

    @pytest.mark.parametrize(
        ("status", "data"),
        [
            (401, {"error": {"message": f"invalid x-api-key {KEY}"}}),
            (403, {"error": {"message": "forbidden"}}),
            (429, {"error": {"message": "slow down, my prompt was Hello"}}),
            (500, {"error": {"message": "boom Hello"}}),
            (400, {"error": {"message": f"bad request for {KEY}: Hello"}}),
            (200, {"content": "Hello"}),
        ],
    )
    def test_errors_and_their_tracebacks_carry_neither_key_prompt_nor_provider_text(
        self,
        fake: FakeProvider,
        caplog: pytest.LogCaptureFixture,
        status: int,
        data: object,
    ) -> None:
        caplog.set_level(logging.DEBUG)
        fake.reply(data, status)

        with pytest.raises(ProviderError) as raised:
            provider(fake).complete("", HELLO, 10)

        everything = "".join(traceback.format_exception(raised.value)) + str(raised.value)
        everything += repr(raised.value) + caplog.text
        assert KEY not in everything
        assert "x-api-key" not in everything.lower()
        assert "Hello" not in everything
        assert "slow down" not in everything
        assert raised.value.__cause__ is None
        # an error raised while handling another one must not show the other one
        assert raised.value.__context__ is None or raised.value.__suppress_context__

    def test_an_unreachable_provider_does_not_leak_the_key_either(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.DEBUG)
        with running() as gone:
            address = gone.url

        with pytest.raises(ProviderError) as raised:
            AnthropicProvider(KEY, MODEL, base_url=address).complete("", HELLO, 10)

        everything = "".join(traceback.format_exception(raised.value)) + caplog.text
        assert KEY not in everything
        assert raised.value.__cause__ is None
        assert raised.value.__suppress_context__
