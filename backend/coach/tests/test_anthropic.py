import json
import logging
import traceback
from typing import Any

import pytest

from coach.providers import transport
from coach.providers.anthropic import API_VERSION, THINKING_ALLOWANCE, AnthropicProvider
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
from season.prompt import SEASON_MAX_TOKENS

from .fake_providers import FakeProvider, message_events, running, sse_body

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


class TestJsonOutput:
    def test_the_flag_changes_nothing_in_the_request(self, fake: FakeProvider) -> None:
        fake.reply(ANSWER)
        provider(fake).complete("", HELLO, 100)
        provider(fake).complete("", HELLO, 100, json_output=True)

        plain, asked = fake.requests
        assert plain["json"] == asked["json"]
        assert "response_format" not in asked["json"]


class TestTheRequest:
    def test_it_goes_to_the_messages_endpoint_with_the_key_and_the_version(
        self, fake: FakeProvider
    ) -> None:
        complete(fake)

        (request,) = fake.requests
        assert request["method"] == "POST"
        assert request["path"] == "/v1/messages"
        assert request["raw_path"] == "/v1/messages"
        assert request["headers"]["accept"] == "text/event-stream"
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
            "max_tokens": 321 + THINKING_ALLOWANCE,
            "system": [
                {
                    "type": "text",
                    "text": "You are a coach.",
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Hi", "cache_control": {"type": "ephemeral"}}
                    ],
                },
                {"role": "assistant", "content": "Hello"},
            ],
            "stream": True,
        }

    def test_an_empty_system_prompt_is_left_out(self, fake: FakeProvider) -> None:
        complete(fake)

        assert "system" not in fake.requests[0]["json"]

    def test_umlauts_and_emoji_arrive_as_they_were_written(self, fake: FakeProvider) -> None:
        fake.reply(ANSWER)

        provider(fake).complete("Größe ✓", [Message("user", "Übung 🏃 für Ältere")], 10)

        body = fake.requests[0]["json"]
        assert body["system"][0]["text"] == "Größe ✓"
        assert body["messages"][0]["content"][0]["text"] == "Übung 🏃 für Ältere"

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

    def test_without_cache_fields_there_are_no_cache_counts(self, fake: FakeProvider) -> None:
        result = complete(fake)

        assert (result.cache_read_tokens, result.cache_write_tokens) == (None, None)

    def test_the_input_is_the_rest_and_the_cached_parts_together(self, fake: FakeProvider) -> None:
        usage = {
            "input_tokens": 20,
            "output_tokens": 5,
            "cache_read_input_tokens": 3000,
            "cache_creation_input_tokens": 400,
        }

        result = complete(fake, {**ANSWER, "usage": usage})

        assert result.input_tokens == 3420
        assert (result.cache_read_tokens, result.cache_write_tokens) == (3000, 400)
        assert result.output_tokens == 5

    @pytest.mark.parametrize(
        ("usage", "expected"),
        [
            ({"input_tokens": 5, "cache_read_input_tokens": 0}, (5, 0, None)),
            ({"input_tokens": 5, "cache_creation_input_tokens": 9}, (14, None, 9)),
            ({"input_tokens": 5, "cache_read_input_tokens": "x"}, (5, None, None)),
            ({"input_tokens": 5, "cache_read_input_tokens": -1}, (5, None, None)),
            ({"input_tokens": 5, "cache_creation_input_tokens": 1.5}, (5, None, None)),
            ({"input_tokens": 5, "cache_read_input_tokens": True}, (5, None, None)),
            ({"cache_read_input_tokens": 100}, (None, 100, None)),
            ({"input_tokens": "5", "cache_read_input_tokens": 100}, (None, 100, None)),
        ],
    )
    def test_cache_counts_that_make_no_sense_are_dropped_one_by_one(
        self, fake: FakeProvider, usage: object, expected: tuple[int | None, int | None, int | None]
    ) -> None:
        result = complete(fake, {**ANSWER, "usage": usage})

        assert (
            result.input_tokens,
            result.cache_read_tokens,
            result.cache_write_tokens,
        ) == expected

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
        monkeypatch.setattr(transport, "MAX_STREAM_BYTES", 200)
        fake.reply({**ANSWER, "content": [{"type": "text", "text": "x" * 500}]})

        with pytest.raises(UnexpectedResponseError, match="larger"):
            provider(fake).complete("", HELLO, 10)

    def test_an_answer_of_exactly_the_limit_is_accepted(
        self, fake: FakeProvider, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake.reply(ANSWER)
        monkeypatch.setattr(transport, "MAX_STREAM_BYTES", len(sse_body(ANSWER)))

        assert provider(fake).complete("", HELLO, 10).text == "Hi there"

    def test_an_answer_that_is_cut_off_is_a_failure_to_reach_the_provider(
        self, fake: FakeProvider
    ) -> None:
        fake.events = message_events(ANSWER)[:-1]
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
    def test_each_line_is_read_with_a_limit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        asked: list[int | None] = []
        lines = sse_body(ANSWER).splitlines(keepends=True)

        class Answer:
            status = 200
            length = None
            headers = {"Content-Type": "text/event-stream"}

            def __enter__(self) -> Answer:
                return self

            def __exit__(self, *args: object) -> None:
                return None

            def readline(self, amount: int = -1) -> bytes:
                asked.append(amount)
                return lines.pop(0) if lines else b""

        monkeypatch.setattr(transport._opener, "open", lambda *a, **k: Answer())

        result = AnthropicProvider(KEY, MODEL, base_url="http://127.0.0.1:1").complete(
            "", HELLO, 10
        )

        assert result.text == "Hi there"
        assert set(asked) == {transport.MAX_LINE_BYTES + 1}


class TestTheStream:
    """The events as the API sends them, beyond what a plain answer turned into events shows."""

    EVENTS: list[object] = [
        {
            "type": "message_start",
            "message": {
                "id": "msg_01",
                "type": "message",
                "role": "assistant",
                "content": [],
                "stop_reason": None,
                "usage": {
                    "input_tokens": 20,
                    "output_tokens": 1,
                    "cache_read_input_tokens": 3000,
                    "cache_creation_input_tokens": 400,
                },
            },
        },
        {"type": "ping"},
        {
            "type": "content_block_start",
            "index": 0,
            "content_block": {"type": "thinking", "thinking": "", "signature": ""},
        },
        {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "thinking_delta", "thinking": "NOT THIS"},
        },
        {"type": "content_block_delta", "index": 0, "delta": {"type": "signature_delta"}},
        {"type": "content_block_stop", "index": 0},
        {"type": "content_block_start", "index": 1, "content_block": {"type": "text", "text": ""}},
        {
            "type": "content_block_delta",
            "index": 1,
            "delta": {"type": "text_delta", "text": '{"a"'},
        },
        {
            "type": "content_block_delta",
            "index": 1,
            "delta": {"type": "text_delta", "text": ": 1}"},
        },
        {"type": "content_block_stop", "index": 1},
        {"type": "a_later_event", "anything": True},
        {
            "type": "message_delta",
            "delta": {"stop_reason": "end_turn"},
            "usage": {"output_tokens": 42},
        },
        {"type": "message_stop"},
    ]

    def stream(self, fake: FakeProvider, events: list[object]) -> Completion:
        fake.events = events
        return provider(fake).complete("", HELLO, 100)

    def test_the_text_and_all_counts_are_put_together(self, fake: FakeProvider) -> None:
        result = self.stream(fake, self.EVENTS)

        assert result == Completion('{"a": 1}', 3420, 42, False, 3000, 400)

    def test_the_stop_reason_of_the_end_says_whether_it_was_cut_off(
        self, fake: FakeProvider
    ) -> None:
        events = [*self.EVENTS]
        events[-2] = {"type": "message_delta", "delta": {"stop_reason": "max_tokens"}}

        assert self.stream(fake, events).truncated is True

    def test_a_stream_that_ends_before_its_end_event_was_cut_off(self, fake: FakeProvider) -> None:
        with pytest.raises(ProviderUnavailableError):
            self.stream(fake, self.EVENTS[:-1])

    @pytest.mark.parametrize(
        ("kind", "expected"),
        [
            ("overloaded_error", ProviderUnavailableError),
            ("api_error", ProviderUnavailableError),
            ("rate_limit_error", RateLimitedError),
            ("authentication_error", InvalidKeyError),
            ("permission_error", InvalidKeyError),
            ("invalid_request_error", UnexpectedResponseError),
            (None, UnexpectedResponseError),
        ],
    )
    def test_an_error_in_the_stream(
        self, fake: FakeProvider, kind: str | None, expected: type[ProviderError]
    ) -> None:
        error = {"type": "error", "error": {"type": kind, "message": "PROVIDER TEXT"}}

        with pytest.raises(expected) as raised:
            self.stream(fake, [*self.EVENTS[:7], error])

        assert "PROVIDER TEXT" not in str(raised.value)

    @pytest.mark.parametrize(
        "events",
        [
            [{"type": "content_block_start", "index": 0, "content_block": {}}],
            ["not an event"],
            [
                EVENTS[0],
                {"type": "content_block_start", "index": 1, "content_block": {"type": "text"}},
            ],
            [
                EVENTS[0],
                {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta"}},
            ],
            [
                EVENTS[0],
                {"type": "content_block_start", "index": 0, "content_block": {"type": "tool_use"}},
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": "x"},
                },
            ],
        ],
    )
    def test_events_that_make_no_sense_are_rejected(
        self, fake: FakeProvider, events: list[object]
    ) -> None:
        with pytest.raises(UnexpectedResponseError):
            self.stream(fake, [*events, {"type": "message_stop"}])

    def test_an_event_that_is_not_json_is_rejected(
        self, fake: FakeProvider, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("coach.tests.fake_providers.sse", lambda data: b"data: {oops\n\n")
        fake.events = [{"type": "message_start"}]

        with pytest.raises(UnexpectedResponseError, match="not JSON"):
            provider(fake).complete("", HELLO, 10)

    def test_a_line_that_is_too_long_is_rejected(
        self, fake: FakeProvider, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(transport, "MAX_LINE_BYTES", 100)

        with pytest.raises(UnexpectedResponseError, match="larger"):
            self.stream(fake, self.EVENTS)

    def test_an_answer_that_keeps_coming_may_take_longer_than_the_timeout(
        self, fake: FakeProvider
    ) -> None:
        fake.events = self.EVENTS
        fake.event_delay = 0.05
        assert len(self.EVENTS) * fake.event_delay > 0.3

        result = provider(fake, timeout=0.3).complete("", HELLO, 100)

        assert result.text == '{"a": 1}'

    def test_a_stream_that_stalls_longer_than_the_timeout_fails(self, fake: FakeProvider) -> None:
        fake.events = self.EVENTS
        fake.event_delay = 1.0

        with pytest.raises(ProviderUnavailableError):
            provider(fake, timeout=0.2).complete("", HELLO, 100)


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

    @pytest.mark.parametrize(
        "bad_key",
        [
            "sk-ant-bad\nX-Injected: 1",
            "sk-ant-bad\rX-Injected: 1",
            "sk-ant-bad\x00key",
            "sk-ant-bad-🔑",
            "sk-ant-bad-ä",
        ],
        ids=["newline", "carriage-return", "nul", "emoji", "non-ascii"],
    )
    def test_invalid_api_key_characters_are_rejected_without_leaking_or_sending(
        self,
        fake: FakeProvider,
        caplog: pytest.LogCaptureFixture,
        bad_key: str,
    ) -> None:
        caplog.set_level(logging.DEBUG)
        fake.reply(ANSWER)

        with pytest.raises(ProviderError) as raised:
            AnthropicProvider(bad_key, MODEL, base_url=fake.url).complete("", HELLO, 10)

        assert type(raised.value) is ProviderError
        assert fake.requests == []
        everything = "".join(traceback.format_exception(raised.value)) + str(raised.value)
        everything += repr(raised.value) + caplog.text
        assert bad_key not in everything
        assert "sk-ant-bad" not in everything
        assert "x-api-key" not in everything.lower()
        assert raised.value.__cause__ is None
        assert raised.value.__context__ is None or raised.value.__suppress_context__


class TestThePromptCache:
    """What is marked for the cache: the system prompt and the first message, five minutes."""

    @staticmethod
    def marks(body: Any) -> int:
        return json.dumps(body).count("cache_control")

    def sent(self, fake: FakeProvider, system: str, messages: list[Message]) -> Any:
        fake.reply(ANSWER)
        provider(fake).complete(system, messages, 100)
        return fake.requests[-1]["json"]

    def test_the_system_prompt_and_the_first_message_end_a_cached_prefix(
        self, fake: FakeProvider
    ) -> None:
        body = self.sent(fake, "Rules.", [Message("user", "Data")])

        assert body["system"][0]["cache_control"] == {"type": "ephemeral"}
        assert body["messages"][0]["content"][0]["cache_control"] == {"type": "ephemeral"}
        assert self.marks(body) == 2

    def test_the_lifetime_is_the_default_of_five_minutes(self, fake: FakeProvider) -> None:
        body = self.sent(fake, "Rules.", [Message("user", "Data")])

        assert "ttl" not in json.dumps(body)

    def test_a_repair_round_starts_with_the_same_bytes_as_the_first_try(
        self, fake: FakeProvider
    ) -> None:
        first = self.sent(fake, "Rules.", [Message("user", "Data")])
        repair = self.sent(
            fake,
            "Rules.",
            [Message("user", "Data"), Message("assistant", "Oops"), Message("user", "Fix it")],
        )

        assert repair["system"] == first["system"]
        assert repair["messages"][0] == first["messages"][0]
        assert repair["messages"][1:] == [
            {"role": "assistant", "content": "Oops"},
            {"role": "user", "content": "Fix it"},
        ]
        assert self.marks(repair) == 2  # never more than the two, whatever the length

    def test_the_text_arrives_unchanged_in_its_blocks(self, fake: FakeProvider) -> None:
        text = 'Käse "quoted" \n 😀 {"json": 1}'

        body = self.sent(fake, text, [Message("user", text)])

        assert body["system"][0]["text"] == text
        assert body["messages"][0]["content"][0]["text"] == text

    def test_without_a_system_prompt_nothing_is_marked(self, fake: FakeProvider) -> None:
        body = self.sent(fake, "", [Message("user", "Reply with the single word: ok")])

        assert self.marks(body) == 0
        assert "system" not in body
        assert body["messages"] == [{"role": "user", "content": "Reply with the single word: ok"}]

    def test_a_first_message_of_the_assistant_is_not_marked(self, fake: FakeProvider) -> None:
        body = self.sent(fake, "Rules.", [Message("assistant", "Hello")])

        assert self.marks(body) == 1
        assert body["messages"] == [{"role": "assistant", "content": "Hello"}]

    def test_the_headers_and_the_version_do_not_change(self, fake: FakeProvider) -> None:
        self.sent(fake, "Rules.", [Message("user", "Data")])

        headers = fake.requests[0]["headers"]
        assert headers["anthropic-version"] == "2023-06-01"
        assert "anthropic-beta" not in headers


class TestTheEffort:
    def test_an_effort_is_sent_in_the_output_config(self, fake: FakeProvider) -> None:
        fake.reply(ANSWER)

        AnthropicProvider(KEY, MODEL, base_url=fake.url, effort="low").complete("", HELLO, 100)

        assert fake.requests[0]["json"]["output_config"] == {"effort": "low"}

    def test_without_an_effort_there_is_no_output_config(self, fake: FakeProvider) -> None:
        complete(fake)

        assert "output_config" not in fake.requests[0]["json"]

    def test_the_thinking_allowance_keeps_the_largest_limit_within_64000_tokens(self) -> None:
        assert SEASON_MAX_TOKENS + THINKING_ALLOWANCE <= 64_000

    def test_the_effort_is_not_shown(self) -> None:
        provider = AnthropicProvider(KEY, MODEL, effort="max")

        assert (
            repr(provider) == f"AnthropicProvider(model={MODEL!r}, base_url={provider._base_url!r})"
        )
