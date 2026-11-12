"""Client for the Intervals.icu API, used with a user's personal API key.

Built on the standard library: a few calls per sync need no connection pooling, and the client
stays small enough to read in one go. The rules it keeps:

- The base URL comes from the settings, never from a request.
- Redirects are not followed, so the key is never sent to another address.
- The whole answer is read with a size limit and only a whitelist of fields is kept.
- Errors say what went wrong, never what was sent: no exception carries the key.
"""

import base64
import http.client
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlsplit

from django.conf import settings

TIMEOUT_SECONDS = 10.0
# The athlete object has about 160 fields and stays far below this.
MAX_RESPONSE_BYTES = 1_000_000

ATHLETE_ID = re.compile(r"[A-Za-z0-9_-]{1,50}")


class IntervalsError(Exception):
    """Base of everything this client raises."""


class InvalidKeyError(IntervalsError):
    """Intervals.icu refused the key (401 or 403)."""


class IntervalsUnavailableError(IntervalsError):
    """Intervals.icu could not be reached or is busy (network, timeout, 429, 5xx); try later."""


class UnexpectedResponseError(IntervalsError):
    """The answer is not what the API documents (status, size or shape)."""


@dataclass(frozen=True)
class Athlete:
    """The only part of the athlete object that is kept; the rest (email, services) is dropped."""

    id: str


class _RefuseRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: object, **kwargs: object) -> None:
        return None  # urllib then reports the 3xx answer as an HTTPError


_opener = urllib.request.build_opener(_RefuseRedirects)


class IntervalsClient:
    def __init__(
        self, api_key: str, *, base_url: str | None = None, timeout: float = TIMEOUT_SECONDS
    ) -> None:
        if not api_key:
            raise ValueError("The API key is empty.")
        self._base_url = (base_url or settings.INTERVALS_API_BASE_URL).rstrip("/")
        if urlsplit(self._base_url).scheme not in {"http", "https"}:
            raise ValueError("The Intervals.icu base URL must start with http:// or https://.")
        self._timeout = timeout
        credentials = base64.b64encode(f"API_KEY:{api_key}".encode()).decode("ascii")
        self._authorization = f"Basic {credentials}"

    def __repr__(self) -> str:
        return f"IntervalsClient(base_url={self._base_url!r})"

    def get_athlete(self) -> Athlete:
        """Check the key and return the account it belongs to (``athlete/0`` means "me")."""
        data = self._get_json("/athlete/0")
        athlete_id = data.get("id") if isinstance(data, dict) else None
        if not isinstance(athlete_id, str) or not ATHLETE_ID.fullmatch(athlete_id):
            raise UnexpectedResponseError("The answer has no usable athlete id.")
        return Athlete(id=athlete_id)

    def _get_json(self, path: str) -> object:
        request = urllib.request.Request(
            self._base_url + path,
            headers={
                "Authorization": self._authorization,
                "Accept": "application/json",
                "User-Agent": "PaceForge",
            },
        )
        try:
            with _opener.open(request, timeout=self._timeout) as response:
                body = response.read(MAX_RESPONSE_BYTES + 1)
                # ``read(n)`` returns what arrived without complaint; bytes still owed mean
                # the connection broke off in the middle of the answer.
                cut_off = bool(response.length)
        except urllib.error.HTTPError as error:
            raise self._for_status(error.code) from None
        except OSError, http.client.HTTPException:
            # Connection refused or reset, DNS, TLS, timeouts, a cut-off answer.
            raise IntervalsUnavailableError("Intervals.icu could not be reached.") from None
        if len(body) > MAX_RESPONSE_BYTES:
            raise UnexpectedResponseError("The answer is larger than expected.")
        if cut_off:
            raise IntervalsUnavailableError("The answer was cut off.")
        try:
            return json.loads(body)
        except ValueError:
            raise UnexpectedResponseError("The answer is not JSON.") from None

    @staticmethod
    def _for_status(status: int) -> IntervalsError:
        if status in {401, 403}:
            return InvalidKeyError("Intervals.icu did not accept the API key.")
        if status == 429 or status >= 500:
            return IntervalsUnavailableError(f"Intervals.icu is not available (HTTP {status}).")
        return UnexpectedResponseError(f"Unexpected answer from Intervals.icu (HTTP {status}).")
