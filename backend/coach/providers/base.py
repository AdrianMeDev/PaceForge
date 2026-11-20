"""What every AI provider offers, and what can go wrong, independent of the provider's API."""

import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable


@dataclass(frozen=True)
class Message:
    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True)
class Completion:
    """The answer of the model. The token counts are ``None`` where the provider did not report
    them. ``input_tokens`` counts the whole input, the cached part included;
    ``cache_read_tokens`` and ``cache_write_tokens`` are the parts of it that were read from and
    written to the provider's prompt cache (``None`` where it did not say, or has no such count).
    ``truncated`` says the answer stopped because ``max_tokens`` was reached, so that a structured
    answer that ends in the middle is not mistaken for a complete one."""

    text: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    truncated: bool = False
    cache_read_tokens: int | None = None
    cache_write_tokens: int | None = None


@dataclass(frozen=True)
class Deadline:
    """The moment by which a request of the athlete must have its answer, on the monotonic clock.
    All the calls and repairs of one request share it, so that together they end before the web
    server gives up on the request and the money is spent on an answer nobody receives."""

    at: float

    @classmethod
    def after(cls, seconds: float) -> Deadline:
        return cls(clock() + seconds)

    def remaining(self) -> float:
        """The seconds left, never below zero."""
        return max(0.0, self.at - clock())

    def passed(self) -> bool:
        return self.remaining() <= 0


def clock() -> float:
    """The clock of the deadlines; tests replace it."""
    return time.monotonic()


@runtime_checkable
class CoachProvider(Protocol):
    """``json_output`` asks the provider to answer with a JSON object where it has a mode for it.
    A provider without one ignores it: the caller reads the answer strictly either way.
    ``deadline``, if given, is when the answer must be there; a provider that has not finished by
    then gives up with a ``DeadlineExceededError``."""

    def complete(
        self,
        system: str,
        messages: Sequence[Message],
        max_tokens: int,
        json_output: bool = False,
        deadline: Deadline | None = None,
    ) -> Completion: ...


class ProviderError(Exception):
    """Base of everything a provider raises. The messages say what went wrong, never what was
    sent or received: no exception carries the key, a prompt or an answer."""


class EndpointNotAllowedError(ProviderError):
    """The address is not (or no longer) one of those the operator allows. Nothing was sent."""


class InvalidKeyError(ProviderError):
    """The provider refused the key (401 or 403)."""


class RateLimitedError(ProviderError):
    """The provider asks to slow down (429). ``retry_after`` is the wait in seconds if it said."""

    def __init__(self, message: str, retry_after: int | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class ProviderUnavailableError(ProviderError):
    """The provider could not be reached or is busy (network, timeout, 408, 5xx); try later."""


class DeadlineExceededError(ProviderUnavailableError):
    """The answer did not arrive before the deadline of the request; the call was given up.
    The provider may still have worked on it (and billed it)."""


class UnexpectedResponseError(ProviderError):
    """The answer is not what the API documents (status, size or shape)."""
