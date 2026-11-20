"""One safe POST with a JSON body, shared by the provider adapters: answered with JSON, or with a
stream of server-sent events.

Built on the standard library, like the Intervals.icu client. The rules it keeps:

- The address comes from the caller (settings or the operator's allow list), never from a request.
- Redirects are not followed, so the key is never sent to another address.
- The whole answer is read with a size limit.
- Errors say what went wrong, never what was sent or received: the body of an error answer is
  not read into a message, and no exception carries a header.
"""

import http.client
import json
import math
import re
import socket
import urllib.error
import urllib.request
from collections.abc import Iterator
from typing import Any

from .base import (
    Deadline,
    DeadlineExceededError,
    InvalidKeyError,
    ProviderError,
    ProviderUnavailableError,
    RateLimitedError,
    UnexpectedResponseError,
)

# A model can think for a while; this is the wait for each step (connect, one read), not a limit
# for the whole call.
TIMEOUT_SECONDS = 60.0
MAX_RESPONSE_BYTES = 2_000_000
# A stream says the same in more bytes: every piece of text comes in an event of its own.
MAX_STREAM_BYTES = 8_000_000
MAX_LINE_BYTES = 1_000_000
# A timeout this close to the deadline is the deadline (the waits are set to the time left).
DEADLINE_SLACK_SECONDS = 1.0
# What a provider asks us to wait is only passed on up to this many seconds.
MAX_RETRY_AFTER = 3600


class _RefuseRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: object, **kwargs: object) -> None:
        return None  # urllib then reports the 3xx answer as an HTTPError


_opener = urllib.request.build_opener(_RefuseRedirects)

_HEADER_NAME_RE = re.compile(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+", re.ASCII)
_HEADER_VALUE_RE = re.compile(r"[\t\x20-\x7e]*", re.ASCII)


def _validate_headers(headers: dict[str, str]) -> None:
    """Refuse a name or a value the standard library would not take, before it sees them.

    ``from None`` on every raise: if we are already handling an error that mentions the key or a
    header, the fixed message must not drag that error into the traceback.
    """
    for name, value in headers.items():
        if not isinstance(name, str) or not _HEADER_NAME_RE.fullmatch(name):
            raise ProviderError("The request headers are not valid.") from None
        if not isinstance(value, str) or not _HEADER_VALUE_RE.fullmatch(value):
            raise ProviderError("The request headers are not valid.") from None


def post_json(
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    *,
    timeout: float = TIMEOUT_SECONDS,
    deadline: Deadline | None = None,
) -> object:
    """The decoded JSON of the answer to ``payload``, or a ``ProviderError``. With a
    ``deadline`` no step waits longer than the time left; nothing is sent once it has passed."""
    try:
        request = _request(url, headers, payload, "application/json")
        wait = _first_wait(timeout, deadline)
        with _opener.open(request, timeout=wait) as response:
            status = response.status
            body = response.read(MAX_RESPONSE_BYTES + 1)
            # ``read(n)`` returns what arrived without complaint; bytes still owed mean the
            # connection broke off in the middle of the answer.
            cut_off = bool(response.length)
    except urllib.error.HTTPError as error:
        raise error_for_status(error.code, error.headers.get("Retry-After")) from None
    except ValueError:
        raise ProviderError("The request could not be prepared.") from None
    except OSError, http.client.HTTPException:
        # Connection refused or reset, DNS, TLS, timeouts, a cut-off answer.
        raise _unreachable(deadline) from None
    if status != 200:
        raise UnexpectedResponseError(f"Unexpected answer from the provider (HTTP {status}).")
    if len(body) > MAX_RESPONSE_BYTES:
        raise UnexpectedResponseError("The answer is larger than expected.")
    if cut_off:
        raise ProviderUnavailableError("The answer was cut off.")
    try:
        return _decode(body)
    except ValueError:
        raise UnexpectedResponseError("The answer is not JSON.") from None


def post_sse(
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    *,
    timeout: float = TIMEOUT_SECONDS,
    deadline: Deadline | None = None,
) -> Iterator[object]:
    """The decoded ``data`` of each server-sent event of the answer to ``payload``, as it arrives,
    or a ``ProviderError``.

    Without a ``deadline``, ``timeout`` is the wait for each step (connect, each read), so an
    answer that takes minutes but keeps coming is not cut short. With one, the connection waits
    at most ``timeout`` and each read waits for the time left: a model may think quietly for a
    while, but the whole answer must be there by the deadline, or ``DeadlineExceededError``.
    A stream that ends before its last byte is a ``ProviderUnavailableError``; whether it ended
    where the API says it should is up to the caller, who knows the events."""
    try:
        request = _request(url, headers, payload, "text/event-stream")
        wait = _first_wait(timeout, deadline)
        with _opener.open(request, timeout=wait) as response:
            if response.status != 200:
                raise UnexpectedResponseError(
                    f"Unexpected answer from the provider (HTTP {response.status})."
                )
            kind = (response.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if kind != "text/event-stream":
                raise UnexpectedResponseError("The answer is not a stream of events.")
            yield from _events(response, deadline)
    except urllib.error.HTTPError as error:
        raise error_for_status(error.code, error.headers.get("Retry-After")) from None
    except ValueError:
        raise ProviderError("The request could not be prepared.") from None
    except OSError, http.client.HTTPException:
        # Connection refused or reset, DNS, TLS, timeouts, a stream that broke off.
        raise _unreachable(deadline) from None


def _first_wait(timeout: float, deadline: Deadline | None) -> float:
    """The wait for connecting; with a deadline that has passed, nothing is sent at all."""
    if deadline is None:
        return timeout
    if deadline.passed():
        raise DeadlineExceededError("There was no time left for the answer.")
    return min(timeout, deadline.remaining())


def _unreachable(deadline: Deadline | None) -> ProviderUnavailableError:
    if deadline is not None and deadline.remaining() < DEADLINE_SLACK_SECONDS:
        return DeadlineExceededError("The answer did not arrive in time.")
    return ProviderUnavailableError("The provider could not be reached.")


def _socket_of(response: object) -> socket.socket | None:
    """The socket under ``response``, so that each read of a stream can wait for the time that
    is left. ``http.client`` keeps it in a private attribute of its file object; should that ever
    change, the reads keep the wait the connection was opened with, and the deadline is still
    checked between them."""
    raw = getattr(getattr(response, "fp", None), "raw", None)
    sock = getattr(raw, "_sock", None)
    return sock if isinstance(sock, socket.socket) else None


def _request(
    url: str, headers: dict[str, str], payload: dict[str, Any], accept: str
) -> urllib.request.Request:
    _validate_headers(headers)
    return urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            **headers,
            "Content-Type": "application/json",
            "Accept": accept,
            "User-Agent": "PaceForge",
        },
    )


def _events(response: http.client.HTTPResponse, deadline: Deadline | None) -> Iterator[object]:
    """The ``data`` of each event, read line by line with the size limits. Only ``data`` lines
    count: the providers put the type of an event into its data as well, and ``event``, ``id``,
    ``retry`` and comments are not needed. An event that the stream does not finish with an empty
    line is dropped, as the format says."""
    total = 0
    lines: list[bytes] = []
    while True:
        if deadline is not None:
            if deadline.passed():
                raise DeadlineExceededError("The answer did not arrive in time.")
            sock = _socket_of(response)
            if sock is not None:
                # Never 0: that would make the socket non-blocking instead of patient.
                sock.settimeout(max(deadline.remaining(), 0.001))
        line = response.readline(MAX_LINE_BYTES + 1)
        if not line:
            break
        total += len(line)
        if total > MAX_STREAM_BYTES or len(line) > MAX_LINE_BYTES:
            raise UnexpectedResponseError("The answer is larger than expected.")
        line = line.rstrip(b"\r\n")
        if not line:
            if lines:
                try:
                    yield _decode(b"\n".join(lines))
                except ValueError:
                    raise UnexpectedResponseError("An event of the answer is not JSON.") from None
                lines = []
        elif line.startswith(b"data:"):
            value = line[len(b"data:") :]
            lines.append(value[1:] if value.startswith(b" ") else value)
    if response.length:
        raise ProviderUnavailableError("The answer was cut off.")


def _decode(raw: bytes) -> object:
    return json.loads(raw, parse_constant=_no_constants, parse_float=_finite_float)


def _no_constants(_: str) -> Any:
    raise ValueError("non-finite constant")


def _finite_float(raw: str) -> float:
    value = float(raw)
    if not math.isfinite(value):
        raise ValueError("non-finite float")
    return value


def error_for_status(status: int, retry_after: str | None = None) -> ProviderError:
    if status in {401, 403}:
        return InvalidKeyError("The provider did not accept the key.")
    if status == 429:
        return RateLimitedError(
            "The provider is rate limiting requests.", retry_after=_seconds(retry_after)
        )
    if status == 408 or status >= 500:
        return ProviderUnavailableError(f"The provider is not available (HTTP {status}).")
    return UnexpectedResponseError(f"Unexpected answer from the provider (HTTP {status}).")


def _seconds(value: str | None) -> int | None:
    """Whole seconds from a ``Retry-After`` header; a date or anything else is ignored."""
    if value is None or not re.fullmatch(r"[0-9]{1,9}", value.strip()):
        return None
    return min(int(value), MAX_RETRY_AFTER)
