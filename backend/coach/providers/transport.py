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


def post_json(
    url: str, headers: dict[str, str], payload: dict[str, Any], *, timeout: float = TIMEOUT_SECONDS
) -> object:
    """The decoded JSON of the answer to ``payload``, or a ``ProviderError``."""
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            **headers,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "PaceForge",
        },
    )
    try:
        with _opener.open(request, timeout=timeout) as response:
            status = response.status
            body = response.read(MAX_RESPONSE_BYTES + 1)
            # ``read(n)`` returns what arrived without complaint; bytes still owed mean the
            # connection broke off in the middle of the answer.
            cut_off = bool(response.length)
    except urllib.error.HTTPError as error:
        raise error_for_status(error.code, error.headers.get("Retry-After")) from None
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
        return json.loads(body)
    except ValueError:
        raise UnexpectedResponseError("The answer is not JSON.") from None


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
