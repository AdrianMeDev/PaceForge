"""Small helpers for goals: what "today" is for a user."""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from accounts.models import User
from athletes.models import AthleteProfile


def _utc_now() -> datetime:
    return datetime.now(UTC)


def today_of(user: User) -> date:
    """The calendar day it is for ``user`` now: in the time zone of their athlete profile, UTC if
    there is none (or the server cannot find it)."""
    name = AthleteProfile.objects.for_user(user).values_list("timezone", flat=True).first()
    try:
        zone = ZoneInfo(name) if name else UTC
    except ZoneInfoNotFoundError, ValueError:
        zone = UTC
    return _utc_now().astimezone(zone).date()
