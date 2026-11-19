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
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, TypeGuard
from urllib.parse import urlsplit

from django.conf import settings

TIMEOUT_SECONDS = 10.0
# The athlete object has about 160 fields and stays far below this.
MAX_RESPONSE_BYTES = 1_000_000
DEFAULT_RETRY_DELAYS: tuple[float, ...] = (1.0, 2.0, 4.0)
MAX_RETRY_AFTER = 60.0

ATHLETE_ID = re.compile(r"[A-Za-z0-9_-]{1,50}")


class IntervalsError(Exception):
    """Base of everything this client raises."""


class InvalidKeyError(IntervalsError):
    """Intervals.icu refused the key (401 or 403)."""


class IntervalsUnavailableError(IntervalsError):
    """Intervals.icu could not be reached or is busy (network, timeout, 429, 5xx); try later."""


class UnexpectedResponseError(IntervalsError):
    """The answer is not what the API documents (status, size or shape)."""


class RejectedError(UnexpectedResponseError):
    """Intervals.icu understood the request and refused it (400 or 422), e.g. a workout it cannot
    parse. Asking again with the same data will not help."""


class NotFoundError(UnexpectedResponseError):
    """There is nothing at that address (404), e.g. an event that was deleted meanwhile."""


@dataclass(frozen=True)
class Athlete:
    """The only part of the athlete object that is kept; the rest (email, services) is dropped."""

    id: str


@dataclass(frozen=True)
class Event:
    """An event of the calendar as Intervals.icu stored it: the only part that is kept."""

    id: int
    external_id: str | None


# Intervals.icu keeps one settings entry per group of sport types. These are the types that make
# an entry the cycling or the running one; every other entry (swimming, "Other", …) is dropped.
RIDE_TYPES = frozenset({"Ride", "VirtualRide"})
RUN_TYPES = frozenset({"Run", "VirtualRun"})

# Generous limits: they only drop nonsense. The athlete profile applies the real ranges.
MAX_POWER_W = 5000
MAX_HEART_RATE = 300
MIN_SPEED_MS = 0.1
MAX_SPEED_MS = 20.0


@dataclass(frozen=True)
class SportSettings:
    """The thresholds of one sport group (``ride`` or ``run``): the only fields that are kept.

    A value that is missing or unusable is ``None``. The pace is in seconds per kilometre;
    Intervals.icu stores it in metres per second.
    """

    sport: str
    ftp: float | None = None
    lthr: float | None = None
    max_hr: float | None = None
    threshold_pace: float | None = None


class _RefuseRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: object, **kwargs: object) -> None:
        return None  # urllib then reports the 3xx answer as an HTTPError


_opener = urllib.request.build_opener(_RefuseRedirects)


class IntervalsClient:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str | None = None,
        timeout: float = TIMEOUT_SECONDS,
        retry_delays: Sequence[float] | None = None,
        sleep: Callable[[float], object] = time.sleep,
    ) -> None:
        if not api_key:
            raise ValueError("The API key is empty.")
        self._base_url = (base_url or settings.INTERVALS_API_BASE_URL).rstrip("/")
        if urlsplit(self._base_url).scheme not in {"http", "https"}:
            raise ValueError("The Intervals.icu base URL must start with http:// or https://.")
        self._timeout = timeout
        configured_delays = getattr(settings, "INTERVALS_RETRY_DELAYS", DEFAULT_RETRY_DELAYS)
        self._retry_delays = tuple(configured_delays if retry_delays is None else retry_delays)
        self._sleep = sleep
        credentials = base64.b64encode(f"API_KEY:{api_key}".encode()).decode("ascii")
        self._authorization = f"Basic {credentials}"

    def __repr__(self) -> str:
        return f"IntervalsClient(base_url={self._base_url!r})"

    def get_athlete(self) -> Athlete:
        """Check the key and return the account it belongs to (``athlete/0`` means "me")."""
        data = self._request("GET", "/athlete/0")
        athlete_id = data.get("id") if isinstance(data, dict) else None
        if not isinstance(athlete_id, str) or not ATHLETE_ID.fullmatch(athlete_id):
            raise UnexpectedResponseError("The answer has no usable athlete id.")
        return Athlete(id=athlete_id)

    def get_sport_settings(self) -> list[SportSettings]:
        """The thresholds for cycling and running (at most one entry each, in that order).

        Anything that does not make sense is skipped, value by value, instead of failing the
        whole call. Where two entries claim the same sport group, the first one wins per value.
        """
        data = self._request("GET", "/athlete/0/sport-settings")
        if not isinstance(data, list):
            raise UnexpectedResponseError("The answer is not a list of sport settings.")
        merged: dict[str, dict[str, float]] = {}
        for entry in data:
            if not isinstance(entry, dict):
                continue
            sport = _sport_group(entry.get("types"))
            if sport is None:
                continue
            found = {
                "ftp": _positive(entry.get("ftp"), MAX_POWER_W),
                "lthr": _positive(entry.get("lthr"), MAX_HEART_RATE),
                "max_hr": _positive(entry.get("max_hr"), MAX_HEART_RATE),
                "threshold_pace": _pace_per_km(entry.get("threshold_pace")),
            }
            current = merged.setdefault(sport, {})
            for name, value in found.items():
                if value is not None and name not in current:
                    current[name] = value
        return [
            SportSettings(sport=sport, **merged[sport])
            for sport in ("ride", "run")
            if sport in merged
        ]

    def upsert_event(self, event: Mapping[str, Any]) -> Event:
        """Create the event, or update the one with the same ``external_id`` (it is the key, so
        sending a workout twice does not give two events). ``event`` is the event as Intervals.icu
        takes it (see ``planning.export``).

        Raises ``RejectedError`` if Intervals.icu does not accept the event. No error shows the
        event or what Intervals.icu answered.
        """
        data = self._request("POST", "/athlete/0/events/bulk?upsert=true", [dict(event)])
        stored = data[0] if isinstance(data, list) and len(data) == 1 else None
        event_id = stored.get("id") if isinstance(stored, dict) else None
        if not _is_event_id(event_id):
            raise UnexpectedResponseError("The answer has no usable event.")
        assert isinstance(stored, dict)
        external_id = stored.get("external_id")
        return Event(id=event_id, external_id=external_id if isinstance(external_id, str) else None)

    def delete_event(self, event_id: int) -> None:
        """Remove an event from the calendar. One that is gone already counts as removed."""
        if not _is_event_id(event_id):
            raise ValueError("An event id is a positive whole number.")
        try:
            self._request("DELETE", f"/athlete/0/events/{event_id}", allow_empty=True)
        except NotFoundError:
            pass

    def _request(
        self, method: str, path: str, payload: object = None, *, allow_empty: bool = False
    ) -> object:
        """One call, whatever the method: the same limits and the same errors for all of them.

        ``payload`` (if any) is sent as JSON. Nothing of it, and nothing of the answer, goes into an
        error. An empty answer is only fine where ``allow_empty`` says so (it gives ``None``).
        """
        headers = {
            "Authorization": self._authorization,
            "Accept": "application/json",
            "User-Agent": "PaceForge",
        }
        data = None
        if payload is not None:
            data = json.dumps(payload).encode()
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            self._base_url + path, data=data, headers=headers, method=method
        )
        for attempt in range(len(self._retry_delays) + 1):
            try:
                with _opener.open(request, timeout=self._timeout) as response:
                    body = response.read(MAX_RESPONSE_BYTES + 1)
                    # ``read(n)`` returns what arrived without complaint; bytes still owed mean
                    # the connection broke off in the middle of the answer.
                    cut_off = bool(response.length)
                break
            except urllib.error.HTTPError as error:
                if _is_retryable_status(error.code) and attempt < len(self._retry_delays):
                    retry_after = _retry_after_seconds(error.headers.get("Retry-After"))
                    delay = retry_after if retry_after is not None else self._retry_delays[attempt]
                    self._sleep(delay)
                    continue
                raise self._for_status(error.code) from None
            except OSError, http.client.HTTPException:
                # Connection refused or reset, DNS, TLS, timeouts, a cut-off answer.
                raise IntervalsUnavailableError("Intervals.icu could not be reached.") from None
        if len(body) > MAX_RESPONSE_BYTES:
            raise UnexpectedResponseError("The answer is larger than expected.")
        if cut_off:
            raise IntervalsUnavailableError("The answer was cut off.")
        if allow_empty and not body.strip():
            return None
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
        if status in {400, 422}:
            return RejectedError(f"Intervals.icu did not accept the request (HTTP {status}).")
        if status == 404:
            return NotFoundError("Intervals.icu has nothing at that address (HTTP 404).")
        return UnexpectedResponseError(f"Unexpected answer from Intervals.icu (HTTP {status}).")


def _is_retryable_status(status: int) -> bool:
    return status == 429 or status >= 500


def _retry_after_seconds(value: str | None) -> float | None:
    """Non-negative seconds from a numeric ``Retry-After`` header, capped at ``MAX_RETRY_AFTER``."""
    if value is None:
        return None
    stripped = value.strip()
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", stripped):
        return None
    return min(float(stripped), MAX_RETRY_AFTER)


def _is_event_id(value: object) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _sport_group(types: object) -> str | None:
    """``ride`` or ``run`` for an entry, ``None`` for any other (or an ambiguous) one."""
    if not isinstance(types, list):
        return None
    names = {name for name in types if isinstance(name, str)}
    rides, runs = bool(names & RIDE_TYPES), bool(names & RUN_TYPES)
    if rides and not runs:
        return "ride"
    if runs and not rides:
        return "run"
    return None


def _positive(value: object, maximum: float) -> float | None:
    # NaN and infinity fail the comparison, so they need no check of their own.
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value) if 0 < value <= maximum else None


def _pace_per_km(speed: object) -> float | None:
    """Seconds per kilometre from the threshold speed in metres per second."""
    metres_per_second = _positive(speed, MAX_SPEED_MS)
    if metres_per_second is None or metres_per_second < MIN_SPEED_MS:
        return None
    return 1000.0 / metres_per_second
