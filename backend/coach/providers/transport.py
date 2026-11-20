"""One safe POST with a JSON body, shared by the provider adapters.

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
import urllib.error
import urllib.request
from typing import Any

from .base import (
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
    url: str, headers: dict[str, str], payload: dict[str, Any], *, timeout: float = TIMEOUT_SECONDS
) -> object:
    """The decoded JSON of the answer to ``payload``, or a ``ProviderError``."""
    _validate_headers(headers)
    body_bytes = json.dumps(payload).encode("utf-8")
    try:
        request = urllib.request.Request(
            url,
            data=body_bytes,
            method="POST",
            headers={
                **headers,
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "PaceForge",
            },
        )
        with _opener.open(request, timeout=timeout) as response:
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
        raise ProviderUnavailableError("The provider could not be reached.") from None
    if status != 200:
        raise UnexpectedResponseError(f"Unexpected answer from the provider (HTTP {status}).")
    if len(body) > MAX_RESPONSE_BYTES:
        raise UnexpectedResponseError("The answer is larger than expected.")
    if cut_off:
        raise ProviderUnavailableError("The answer was cut off.")
    try:
        return json.loads(body, parse_constant=_no_constants, parse_float=_finite_float)
    except ValueError:
        raise UnexpectedResponseError("The answer is not JSON.") from None


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
