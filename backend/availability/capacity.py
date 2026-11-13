"""How much time a user can train: on one day and in one week.

The weekday minutes are the starting point, a day inside an absence offers nothing, and the weekly
budget caps what the week adds up to. Nothing declared means no time (not "unlimited"). The
functions take calendar days: which day it is for the user is the caller's business.
"""

from datetime import date, timedelta

from accounts.models import User

from .models import AvailabilitySettings, UnavailablePeriod, WeekdayMinutes


def minutes_on(user: User, day: date) -> int:
    """The minutes ``user`` can train on ``day``; the weekly budget does not apply to a day."""
    return _days(user, day, 1)[0]


def minutes_in_week(user: User, monday: date) -> int:
    """The minutes ``user`` can train in the week that starts on ``monday``: the seven days added
    up, at most the weekly budget if there is one."""
    if monday.weekday() != 0:
        raise ValueError(f"{monday} is not a Monday")
    total = sum(_days(user, monday, 7))
    budget = (
        AvailabilitySettings.objects.for_user(user)
        .values_list("weekly_budget_minutes", flat=True)
        .first()
    )
    return total if budget is None else min(total, budget)


def _days(user: User, first: date, count: int) -> list[int]:
    """The minutes of ``count`` days from ``first`` on, from two queries however many days."""
    last = first + timedelta(days=count - 1)
    per_weekday = dict(WeekdayMinutes.objects.for_user(user).values_list("weekday", "minutes"))
    absences = list(
        UnavailablePeriod.objects.for_user(user)
        .filter(start_date__lte=last, end_date__gte=first)
        .values_list("start_date", "end_date")
    )
    days = [first + timedelta(days=offset) for offset in range(count)]
    return [
        0
        if any(start <= day <= end for start, end in absences)
        else per_weekday.get(day.weekday(), 0)
        for day in days
    ]
