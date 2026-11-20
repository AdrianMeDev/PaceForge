"""The Anthropic Messages API, used with a user's own key.

Answers are streamed: a strong model can think and write for minutes, and a request that waits
for the whole answer in one read would give up while the provider keeps working (and billing).
"""

from collections.abc import Iterable, Sequence
from typing import Any

from django.conf import settings

from .base import (
    Completion,
    Deadline,
    InvalidKeyError,
    Message,
    ProviderError,
    ProviderUnavailableError,
    RateLimitedError,
    UnexpectedResponseError,
)
from .transport import TIMEOUT_SECONDS, post_sse

API_VERSION = "2023-06-01"

# Thinking counts towards ``max_tokens``, and newer models always think. The callers give the size
# of the answer they expect; this much is added for the thinking before it, so that the answer is
# not cut off. Only what the model writes is billed, and streaming keeps a large limit from timing
# out. The sum stays within the 64,000 output tokens of the smallest current models.
THINKING_ALLOWANCE = 16_000

# The prompt cache: everything up to a marked block is stored for five minutes, and a request that
# starts with the same bytes reads it for a tenth of the price of reading it again.
CACHE_MARK = {"type": "ephemeral"}


class AnthropicProvider:
    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        base_url: str | None = None,
        timeout: float = TIMEOUT_SECONDS,
        effort: str = "",
    ) -> None:
        if not api_key:
            raise ValueError("The API key is empty.")
        if not model:
            raise ValueError("The model is empty.")
        self._api_key = api_key
        self._model = model
        self._base_url = (base_url or settings.ANTHROPIC_API_BASE_URL).rstrip("/")
        self._timeout = timeout
        self._effort = effort

    def __repr__(self) -> str:
        return f"AnthropicProvider(model={self._model!r}, base_url={self._base_url!r})"

    def complete(
        self,
        system: str,
        messages: Sequence[Message],
        max_tokens: int,
        json_output: bool = False,
        deadline: Deadline | None = None,
    ) -> Completion:
        # The Messages API has no JSON mode that fits a plain request: the flag is ignored.
        if not messages:
            raise ValueError("There is nothing to send.")
        if max_tokens < 1:
            raise ValueError("max_tokens must be at least 1.")
        payload: dict[str, object] = {
            "model": self._model,
            "max_tokens": max_tokens + THINKING_ALLOWANCE,
            "messages": _messages(messages, cached=bool(system)),
            "stream": True,
        }
        if self._effort:
            # Not every model takes every level; one that does not refuses the request.
            payload["output_config"] = {"effort": self._effort}
        if system:
            # The same for every request of one purpose, so that the next week, the next try and
            # the next review read it from the cache.
            payload["system"] = [{"type": "text", "text": system, "cache_control": CACHE_MARK}]
        events = post_sse(
            f"{self._base_url}/v1/messages",
            {"x-api-key": self._api_key, "anthropic-version": API_VERSION},
            payload,
            timeout=self._timeout,
            deadline=deadline,
        )
        return _completion(_assemble(events))


def _messages(messages: Sequence[Message], *, cached: bool) -> list[dict[str, object]]:
    """The messages as the API takes them. With ``cached`` the first message (the briefing, the
    plan and the wish: what the repair rounds of one conversation have in common) is a block that
    ends a cached prefix; the others are plain text. A request without a system prompt (the
    connection check) caches nothing: a few tokens are below any minimum anyway."""
    body: list[dict[str, object]] = []
    for index, message in enumerate(messages):
        if cached and index == 0 and message.role == "user":
            block = {"type": "text", "text": message.content, "cache_control": CACHE_MARK}
            body.append({"role": message.role, "content": [block]})
        else:
            body.append({"role": message.role, "content": message.content})
    return body


def _assemble(events: Iterable[object]) -> object:
    """The message the events describe, in the shape the API answers with when it does not
    stream, so that one set of checks reads both.

    ``message_start`` carries the message without its content, each ``content_block_start`` adds
    a block, a ``text_delta`` adds to the text of its block, ``message_delta`` brings the stop
    reason and the final counts, and ``message_stop`` ends it. A stream that ends earlier was cut
    off. ``ping``, ``content_block_stop``, other deltas (thinking, signatures) and event types the
    API adds later are skipped."""
    message: dict[str, Any] | None = None
    for event in events:
        if not isinstance(event, dict):
            raise UnexpectedResponseError("An event of the answer is not an object.")
        kind = event.get("type")
        if kind == "error":
            raise _stream_error(event.get("error"))
        if kind == "message_start":
            started = event.get("message")
            if not isinstance(started, dict):
                raise UnexpectedResponseError("The answer is not an object.")
            message = dict(started)
            if isinstance(message.get("content"), list):
                message["content"] = list(message["content"])
        elif message is None:
            if kind != "ping":
                raise UnexpectedResponseError("The answer did not start with a message.")
        elif kind == "content_block_start":
            _start_block(message, event)
        elif kind == "content_block_delta":
            _add_text(message, event)
        elif kind == "message_delta":
            delta = event.get("delta")
            if isinstance(delta, dict) and "stop_reason" in delta:
                message["stop_reason"] = delta["stop_reason"]
            usage = event.get("usage")
            if isinstance(usage, dict):
                # The counts here are the totals so far; they replace those of the start.
                before = message.get("usage")
                message["usage"] = {**(before if isinstance(before, dict) else {}), **usage}
        elif kind == "message_stop":
            return message
    raise ProviderUnavailableError("The answer was cut off.")


def _start_block(message: dict[str, Any], event: dict[str, Any]) -> None:
    content = message.get("content")
    if not isinstance(content, list) or event.get("index") != len(content):
        raise UnexpectedResponseError("A block of the answer is out of order.")
    block = event.get("content_block")
    content.append(dict(block) if isinstance(block, dict) else block)


def _add_text(message: dict[str, Any], event: dict[str, Any]) -> None:
    delta = event.get("delta")
    if not isinstance(delta, dict) or delta.get("type") != "text_delta":
        return
    content = message.get("content")
    index = event.get("index")
    text = delta.get("text")
    if (
        not isinstance(content, list)
        or not isinstance(index, int)
        or isinstance(index, bool)
        or not 0 <= index < len(content)
        or not isinstance(text, str)
    ):
        raise UnexpectedResponseError("A piece of the answer belongs to no block.")
    block = content[index]
    if not isinstance(block, dict) or not isinstance(block.get("text"), str):
        raise UnexpectedResponseError("A piece of the answer belongs to no text block.")
    block["text"] += text


def _stream_error(error: object) -> ProviderError:
    """An error the provider reports after the stream began. Only its type is read; the text
    of the provider is never passed on."""
    kind = error.get("type") if isinstance(error, dict) else None
    if kind in {"overloaded_error", "api_error"}:
        return ProviderUnavailableError("The provider is not available.")
    if kind == "rate_limit_error":
        return RateLimitedError("The provider is rate limiting requests.")
    if kind in {"authentication_error", "permission_error"}:
        return InvalidKeyError("The provider did not accept the key.")
    return UnexpectedResponseError("The provider reported an error in its answer.")


def _completion(data: object) -> Completion:
    if not isinstance(data, dict):
        raise UnexpectedResponseError("The answer is not an object.")
    blocks = data.get("content")
    if not isinstance(blocks, list):
        raise UnexpectedResponseError("The answer has no content.")
    texts = [
        block["text"]
        for block in blocks
        if isinstance(block, dict)
        and block.get("type") == "text"
        and isinstance(block.get("text"), str)
    ]
    text = "".join(texts)
    if not text:
        raise UnexpectedResponseError("The answer has no text.")
    usage = data.get("usage")
    usage = usage if isinstance(usage, dict) else {}
    rest = _count(usage.get("input_tokens"))
    read = _count(usage.get("cache_read_input_tokens"))
    written = _count(usage.get("cache_creation_input_tokens"))
    return Completion(
        text=text,
        # The API counts only what is not from the cache as input; the whole input is that and
        # the cached parts, so that the number means the same as for every other provider.
        input_tokens=None if rest is None else rest + (read or 0) + (written or 0),
        output_tokens=_count(usage.get("output_tokens")),
        truncated=data.get("stop_reason") == "max_tokens",
        cache_read_tokens=read,
        cache_write_tokens=written,
    )


def _count(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None
