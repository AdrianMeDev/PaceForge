"""The facts a week plan is checked against: what the user can do, have and did.

``build_context`` collects them from the database for one user and one week; the checks themselves
(``planning.rules``) are pure functions on a plan and this context. Nothing is invented: a fact the
user has not given is simply not there (no time declared means no time, no threshold means no zone
system, no activities means no reference volume).
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, tzinfo

from accounts.models import User
from activities.models import Activity
from athletes.thresholds import all_candidates
from availability.capacity import week_capacity
from goals.services import time_zone_of

from .schema import Sport, ZoneSystem

# How many weeks before the plan's week make up the reference volume.
RECENT_WEEKS = 4


@dataclass(frozen=True)
class PlanContext:
    week_start: date
    # What each day offers, Monday first; 0 inside an absence. The weekly budget is not in here.
    minutes: tuple[int, ...]
    # The kind of absence that covers each day, else ``None``.
    absences: tuple[str | None, ...]
    # The weekly budget (``None``: none) and what the week offers in all, budget applied.
    weekly_budget: int | None
    weekly_minutes: int
    # The (sport, zone system) pairs the athlete has a threshold for.
    zone_systems: frozenset[tuple[Sport, ZoneSystem]]
    # Minutes done in each of the up to ``RECENT_WEEKS`` weeks before this one that have data,
    # the latest week first. Empty: there is no reference.
    recent_weeks: tuple[int, ...]
    # What the athlete calls a normal week, in minutes (``None``: not said). The progression rule
    # takes it as the reference when it is higher than the recent weeks.
    typical_weekly_minutes: int | None = None

    def offset(self, day: date) -> int | None:
        """The place of ``day`` in the week (Monday is 0), ``None`` if it lies outside."""
        offset = (day - self.week_start).days
        return offset if 0 <= offset < 7 else None


def build_context(user: User, monday: date) -> PlanContext:
    """The context of the week that starts on ``monday``: seven queries however full the data."""
    capacity = week_capacity(user, monday)  # raises ValueError unless it is a Monday
    held = set(all_candidates(user))
    zone = time_zone_of(user)
    return PlanContext(
        week_start=monday,
        minutes=capacity.minutes,
        absences=capacity.absences,
        weekly_budget=capacity.budget,
        weekly_minutes=capacity.total,
        zone_systems=usable_zone_systems(held),
        recent_weeks=recent_weekly_minutes(_recent_activities(user, monday, zone), zone, monday),
        typical_weekly_minutes=capacity.typical_weekly_minutes,
    )


def usable_zone_systems(held: Iterable[tuple[str, str]]) -> frozenset[tuple[Sport, ZoneSystem]]:
    """The zone systems that can be used for a sport, given the thresholds the athlete has
    (``(sport group, metric)`` pairs such as ``("ride", "ftp")``). Power needs the FTP, pace the
    threshold pace and heart rate the lactate threshold or the maximum heart rate. Swimming and
    strength have no zones."""
    held = set(held)
    systems: set[tuple[Sport, ZoneSystem]] = set()
    if ("ride", "ftp") in held:
        systems.add((Sport.CYCLING, ZoneSystem.POWER))
    if ("ride", "lthr") in held or ("ride", "max_hr") in held:
        systems.add((Sport.CYCLING, ZoneSystem.HEART_RATE))
    if ("run", "threshold_pace") in held:
        systems.add((Sport.RUNNING, ZoneSystem.PACE))
    if ("run", "lthr") in held or ("run", "max_hr") in held:
        systems.add((Sport.RUNNING, ZoneSystem.HEART_RATE))
    return frozenset(systems)


def recent_weekly_minutes(
    activities: Iterable[tuple[datetime, float | None, float | None]],
    zone: tzinfo,
    monday: date,
    weeks: int = RECENT_WEEKS,
) -> tuple[int, ...]:
    """The minutes done in each of the ``weeks`` weeks before ``monday``, the latest first.

    ``activities`` are ``(start, timer seconds, elapsed seconds)``. A week is a calendar week
    (Monday to Sunday) in ``zone``, so an activity just after midnight belongs to the day the
    athlete lived it. The timer time counts, the elapsed time stands in for it, and an activity
    with neither has no duration and does not count at all. A week without any activity that has
    a duration is left out, not counted as zero: it says nothing about what the athlete can do.
    """
    first = monday - timedelta(weeks=weeks)
    seconds_by_week: dict[date, float] = {}
    for start, timer, elapsed in activities:
        duration = timer if timer is not None else elapsed
        if duration is None:
            continue
        day = start.astimezone(zone).date()
        if not first <= day < monday:
            continue
        week = day - timedelta(days=day.weekday())
        seconds_by_week[week] = seconds_by_week.get(week, 0.0) + duration
    return tuple(
        int(seconds_by_week[week] / 60 + 0.5) for week in sorted(seconds_by_week, reverse=True)
    )


def _recent_activities(
    user: User, monday: date, zone: tzinfo
) -> list[tuple[datetime, float | None, float | None]]:
    """The user's activities of the weeks before ``monday``, with one query."""
    since = _local_midnight(monday - timedelta(weeks=RECENT_WEEKS), zone)
    until = _local_midnight(monday, zone)
    return list(
        Activity.objects.for_user(user)
        .filter(start_time__gte=since, start_time__lt=until)
        .values_list("start_time", "timer_seconds", "elapsed_seconds")
    )


def _local_midnight(day: date, zone: tzinfo) -> datetime:
    return datetime.combine(day, time.min, tzinfo=zone).astimezone(UTC)
