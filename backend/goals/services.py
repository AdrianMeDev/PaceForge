"""Small helpers for goals: what "today" is for a user."""

from datetime import UTC, date, datetime, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from accounts.models import User
from athletes.models import AthleteProfile


def _utc_now() -> datetime:
    return datetime.now(UTC)


def time_zone_of(user: User) -> tzinfo:
    """The time zone of ``user``'s athlete profile, UTC if there is none (or the server cannot
    find it)."""
    name = AthleteProfile.objects.for_user(user).values_list("timezone", flat=True).first()
    try:
        return ZoneInfo(name) if name else UTC
    except ZoneInfoNotFoundError, ValueError:
        return UTC


def today_of(user: User) -> date:
    """The calendar day it is for ``user`` now, in their time zone."""
    return _utc_now().astimezone(time_zone_of(user)).date()
