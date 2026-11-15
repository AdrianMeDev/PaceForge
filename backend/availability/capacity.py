"""How much time a user can train: on one day and in one week.

The weekday minutes are the starting point, a day inside an absence offers nothing, and the weekly
budget caps what the week adds up to. Nothing declared means no time (not "unlimited"). A weekday
also says whether two sessions are allowed and in which parts of the day: where nothing is said,
two are allowed and every part of the day is open. The functions take calendar days: which day it
is for the user is the caller's business.
"""

from dataclasses import dataclass
from datetime import date, timedelta

from accounts.models import User

from .intensity import DEFAULT_LEVEL, LEVEL_LIMITS, LIMIT_NAMES, Limits, effective_limits
from .models import (
    SLOTS,
    SPORTS,
    AvailabilitySettings,
    UnavailablePeriod,
    WeekdayMinutes,
    effective_slots,
    effective_sports,
)

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
    # What the user calls a normal week of training, ``None`` if not said. A reference for the
    # planning, not a limit: it changes nothing about what the week offers.
    typical_weekly_minutes: int | None = None
    # The sports the user wants in a plan (all of them if none was chosen) and whether stretching
    # may be added to sessions. Choices, not time: they change nothing about what the week offers.
    sports: tuple[str, ...] = SPORTS
    stretching: bool = False
    # The limits of the planning rules: the user's intensity level with their own values.
    limits: Limits = LEVEL_LIMITS[DEFAULT_LEVEL]
    # Per day, Monday first: whether two sessions are allowed, and the parts of the day that are
    # open (in the order of the day). Choices, not time: they change nothing about the minutes.
    double_days: tuple[bool, ...] = (True,) * 7
    time_windows: tuple[tuple[str, ...], ...] = (SLOTS,) * 7


def week_capacity(user: User, monday: date) -> WeekCapacity:
    """What the week that starts on ``monday`` offers: three queries however full the week."""
    if monday.weekday() != 0:
        raise ValueError(f"{monday} is not a Monday")
    days = _load(user, monday, 7)
    minutes = tuple(day.minutes for day in days)
    row = (
        AvailabilitySettings.objects.for_user(user)
        .values_list(
            "weekly_budget_minutes",
            "typical_weekly_minutes",
            "sports",
            "stretching",
            "intensity_level",
            *LIMIT_NAMES,
        )
        .first()
    )
    if row is None:
        budget, typical, chosen, stretching = None, None, [], False
        limits = LEVEL_LIMITS[DEFAULT_LEVEL]
    else:
        budget, typical, chosen, stretching, level, *own = row
        limits = effective_limits(level, dict(zip(LIMIT_NAMES, own, strict=True)))
    total = sum(minutes)
    return WeekCapacity(
        minutes=minutes,
        absences=tuple(day.absence for day in days),
        budget=budget,
        total=total if budget is None else min(total, budget),
        typical_weekly_minutes=typical,
        sports=tuple(effective_sports(chosen)),
        stretching=stretching,
        limits=limits,
        double_days=tuple(day.double_allowed for day in days),
        time_windows=tuple(day.slots for day in days),
    )


def minutes_on(user: User, day: date) -> int:
    """The minutes ``user`` can train on ``day``; the weekly budget does not apply to a day."""
    return _load(user, day, 1)[0].minutes


def minutes_in_week(user: User, monday: date) -> int:
    """The minutes ``user`` can train in the week that starts on ``monday``: the seven days added
    up, at most the weekly budget if there is one."""
    return week_capacity(user, monday).total


@dataclass(frozen=True)
class _Day:
    minutes: int
    absence: str | None
    double_allowed: bool
    slots: tuple[str, ...]


def _load(user: User, first: date, count: int) -> list[_Day]:
    """What ``count`` days from ``first`` on offer, from two queries however many."""
    last = first + timedelta(days=count - 1)
    per_weekday = {
        weekday: (minutes, double_allowed, tuple(effective_slots(slots)))
        for weekday, minutes, double_allowed, slots in WeekdayMinutes.objects.for_user(
            user
        ).values_list("weekday", "minutes", "double_allowed", "slots")
    }
    absences = list(
        UnavailablePeriod.objects.for_user(user)
        .filter(start_date__lte=last, end_date__gte=first)
        .values_list("start_date", "end_date", "kind")
    )
    result: list[_Day] = []
    for offset in range(count):
        day = first + timedelta(days=offset)
        offered, double_allowed, slots = per_weekday.get(day.weekday(), (0, True, SLOTS))
        kinds = {kind for start, end, kind in absences if start <= day <= end}
        if kinds:
            result.append(_Day(0, min(kinds, key=_rank), double_allowed, slots))
        else:
            result.append(_Day(offered, None, double_allowed, slots))
    return result


def _rank(kind: str) -> int:
    return _KIND_ORDER.index(kind) if kind in _KIND_ORDER else len(_KIND_ORDER)
