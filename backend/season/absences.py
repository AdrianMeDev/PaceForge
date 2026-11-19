"""The absences of a user that overlap a stretch of days, in one query and scoped to the user.

Only what the season page needs: the kind and the two dates, never the note of the athlete.
"""

from datetime import date, timedelta
from typing import Any

from accounts.models import User
from availability.models import UnavailablePeriod


def absences_between(user: User, first: date, last: date) -> list[dict[str, Any]]:
    """The periods of ``user`` that touch the days ``first`` to ``last`` (both included), by start
    date, then by end date, then by id."""
    rows = (
        UnavailablePeriod.objects.for_user(user)
        .filter(start_date__lte=last, end_date__gte=first)
        .order_by("start_date", "end_date", "id")
        .values_list("kind", "start_date", "end_date")
    )
    return [
        {"kind": kind, "start_date": start_date.isoformat(), "end_date": end_date.isoformat()}
        for kind, start_date, end_date in rows
    ]


def absences_in_weeks(user: User, week_starts: list[date]) -> list[dict[str, Any]]:
    """The absences overlapping any of the weeks that start on ``week_starts`` (each week is seven
    days from its Monday). An empty list of weeks means no query and no absence."""
    if not week_starts:
        return []
    return absences_between(user, min(week_starts), max(week_starts) + timedelta(days=6))
