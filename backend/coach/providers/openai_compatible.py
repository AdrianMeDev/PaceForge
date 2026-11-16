"""The chat completions API of OpenAI and of everything that copies it (Ollama, llama.cpp ...).

The address is only ever one the operator has allowed: users must not point the server at
arbitrary internal addresses. The key is optional, local servers usually need none.
"""

from collections.abc import Sequence
from urllib.parse import urlsplit

from django.conf import settings

from .base import Completion, EndpointNotAllowedError, Message, UnexpectedResponseError
from .transport import TIMEOUT_SECONDS, post_json

# The hosts known to take ``response_format: {"type": "json_object"}``. Deliberately a short list
# and not "every address": a router such as OpenRouter depends on the model behind it, and a
# server that does not know the field may refuse the request. DeepSeek documents the mode (the
# prompt has to say "JSON", and the answer may now and then come back empty).
JSON_MODE_HOSTS = frozenset({"api.deepseek.com"})


class OpenAICompatibleProvider:
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str = "",
        *,
        timeout: float = TIMEOUT_SECONDS,
    ) -> None:
        if not model:
            raise ValueError("The model is empty.")
        # The same text as in the allow list, checked here again: the operator may have taken
        # the address off the list since it was chosen.
        if base_url not in settings.AI_ALLOWED_BASE_URLS:
            raise EndpointNotAllowedError("This address is not allowed on this server.")
        self._base_url = base_url
        self._model = model
        self._api_key = api_key
        self._timeout = timeout

    def __repr__(self) -> str:
        return f"OpenAICompatibleProvider(model={self._model!r}, base_url={self._base_url!r})"

    def complete(
        self,
        system: str,
        messages: Sequence[Message],
        max_tokens: int,
        json_output: bool = False,
    ) -> Completion:
        if not messages:
            raise ValueError("There is nothing to send.")
        if max_tokens < 1:
            raise ValueError("max_tokens must be at least 1.")
        chat = [{"role": m.role, "content": m.content} for m in messages]
        if system:
            chat.insert(0, {"role": "system", "content": system})
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
        payload: dict[str, object] = {
            "model": self._model,
            "max_tokens": max_tokens,
            "messages": chat,
        }
        if json_output and urlsplit(self._base_url).hostname in JSON_MODE_HOSTS:
            payload["response_format"] = {"type": "json_object"}
        data = post_json(
            f"{self._base_url}/chat/completions", headers, payload, timeout=self._timeout
        )
        return _completion(data)


def _completion(data: object) -> Completion:
    if not isinstance(data, dict):
        raise UnexpectedResponseError("The answer is not an object.")
    choices = data.get("choices")
    first = choices[0] if isinstance(choices, list) and choices else None
    message = first.get("message") if isinstance(first, dict) else None
    text = message.get("content") if isinstance(message, dict) else None
    if not isinstance(text, str) or not text:
        raise UnexpectedResponseError("The answer has no text.")
    usage = data.get("usage")
    usage = usage if isinstance(usage, dict) else {}
    details = usage.get("prompt_tokens_details")
    details = details if isinstance(details, dict) else {}
    return Completion(
        text=text,
        input_tokens=_count(usage.get("prompt_tokens")),
        output_tokens=_count(usage.get("completion_tokens")),
        truncated=isinstance(first, dict) and first.get("finish_reason") == "length",
        # OpenAI caches a long prefix on its own and says how much of the prompt it read; the
        # request does not ask for it, and most servers on your own hardware say nothing.
        cache_read_tokens=_count(details.get("cached_tokens")),
    )


def _count(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None
