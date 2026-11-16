"""The Anthropic Messages API, used with a user's own key."""

from collections.abc import Sequence

from django.conf import settings

from .base import Completion, Message, UnexpectedResponseError
from .transport import TIMEOUT_SECONDS, post_json

API_VERSION = "2023-06-01"

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
    ) -> None:
        if not api_key:
            raise ValueError("The API key is empty.")
        if not model:
            raise ValueError("The model is empty.")
        self._api_key = api_key
        self._model = model
        self._base_url = (base_url or settings.ANTHROPIC_API_BASE_URL).rstrip("/")
        self._timeout = timeout

    def __repr__(self) -> str:
        return f"AnthropicProvider(model={self._model!r}, base_url={self._base_url!r})"

    def complete(
        self,
        system: str,
        messages: Sequence[Message],
        max_tokens: int,
        json_output: bool = False,
    ) -> Completion:
        # The Messages API has no JSON mode that fits a plain request: the flag is ignored.
        if not messages:
            raise ValueError("There is nothing to send.")
        if max_tokens < 1:
            raise ValueError("max_tokens must be at least 1.")
        payload: dict[str, object] = {
            "model": self._model,
            "max_tokens": max_tokens,
            "messages": _messages(messages, cached=bool(system)),
        }
        if system:
            # The same for every request of one purpose, so that the next week, the next try and
            # the next review read it from the cache.
            payload["system"] = [{"type": "text", "text": system, "cache_control": CACHE_MARK}]
        data = post_json(
            f"{self._base_url}/v1/messages",
            {"x-api-key": self._api_key, "anthropic-version": API_VERSION},
            payload,
            timeout=self._timeout,
        )
        return _completion(data)


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
