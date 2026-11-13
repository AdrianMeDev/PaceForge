"""How much time a user can train: on one day and in one week.

The weekday minutes are the starting point, a day inside an absence offers nothing, and the weekly
budget caps what the week adds up to. Nothing declared means no time (not "unlimited"). The
functions take calendar days: which day it is for the user is the caller's business.
"""

from dataclasses import dataclass
from datetime import date, timedelta

from accounts.models import User

from .models import AvailabilitySettings, UnavailablePeriod, WeekdayMinutes

# Where absences overlap, the one that says most is named: illness before vacation before the rest.
_KIND_ORDER = ("illness", "vacation", "other")


@dataclass(frozen=True)
class WeekCapacity:
    """What a week offers, from Monday to Sunday."""

    # Minutes per day, 0 inside an absence; the weekly budget is not applied to single days.
    minutes: tuple[int, ...]
    # The kind of absence that covers the day (``illness``, ``vacation``, ``other``), else ``None``.
    absences: tuple[str | None, ...]
    # The weekly budget, ``None`` for no cap.
    budget: int | None
    # The days added up, at most the budget.
    total: int


def week_capacity(user: User, monday: date) -> WeekCapacity:
    """What the week that starts on ``monday`` offers: three queries however full the week."""
    if monday.weekday() != 0:
        raise ValueError(f"{monday} is not a Monday")
    days = _load(user, monday, 7)
    minutes = tuple(offered for offered, _ in days)
    budget = (
        AvailabilitySettings.objects.for_user(user)
        .values_list("weekly_budget_minutes", flat=True)
        .first()
    )
    total = sum(minutes)
    return WeekCapacity(
        minutes=minutes,
        absences=tuple(kind for _, kind in days),
        budget=budget,
        total=total if budget is None else min(total, budget),
    )


def minutes_on(user: User, day: date) -> int:
    """The minutes ``user`` can train on ``day``; the weekly budget does not apply to a day."""
    return _load(user, day, 1)[0][0]


def minutes_in_week(user: User, monday: date) -> int:
    """The minutes ``user`` can train in the week that starts on ``monday``: the seven days added
    up, at most the weekly budget if there is one."""
    return week_capacity(user, monday).total


def _load(user: User, first: date, count: int) -> list[tuple[int, str | None]]:
    """Minutes and absence of ``count`` days from ``first`` on, from two queries however many."""
    last = first + timedelta(days=count - 1)
    per_weekday = dict(WeekdayMinutes.objects.for_user(user).values_list("weekday", "minutes"))
    absences = list(
        UnavailablePeriod.objects.for_user(user)
        .filter(start_date__lte=last, end_date__gte=first)
        .values_list("start_date", "end_date", "kind")
    )
    result: list[tuple[int, str | None]] = []
    for offset in range(count):
        day = first + timedelta(days=offset)
        kinds = {kind for start, end, kind in absences if start <= day <= end}
        if kinds:
            result.append((0, min(kinds, key=_rank)))
        else:
            result.append((per_weekday.get(day.weekday(), 0), None))
    return result


def _rank(kind: str) -> int:
    return _KIND_ORDER.index(kind) if kind in _KIND_ORDER else len(_KIND_ORDER)
