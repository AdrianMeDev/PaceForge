"""The checks of a filled season: does it follow the skeleton it was made for?

The coach may ignore the frame it was given, so what is usable is decided here, by code. Every
check returns findings with a stable code, a path into the plan and a fixed text made from numbers,
dates and the words of the format: nothing the coach wrote is ever repeated. An **error** makes
the plan unfit to confirm, a **warning** is for the athlete to weigh. The findings and the report
are those of the week plan (``planning.rules``, ``planning.validation``).

Pure: no database. What the checks need comes in as a ``SeasonContext``.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date

from planning.rules import Finding, Severity
from planning.schema import Sport
from planning.validation import Report

from .schema import PlanWeek, SeasonPlan, SessionKind
from .skeleton import Skeleton, SkeletonWeek

# The minutes of a week may differ from the target of the skeleton by this much, in percent, in
# either direction. The skeleton is a frame, not a promise to the minute.
WINDOW_PERCENT = 10


@dataclass(frozen=True)
class SeasonContext:
    """What a filled season is checked against: the skeleton and the sports the athlete wants."""

    skeleton: Skeleton
    sports: frozenset[Sport] = field(default_factory=lambda: frozenset(Sport))


Check = Callable[[SeasonPlan, SeasonContext], list[Finding]]


def window(target: int) -> tuple[int, int]:
    """The least and the most minutes a week with ``target`` may have (both ends included): the
    target minus and plus ``WINDOW_PERCENT``, rounded towards the target."""
    low = (target * (100 - WINDOW_PERCENT) + 99) // 100
    high = target * (100 + WINDOW_PERCENT) // 100
    return low, high


def _matched(plan: SeasonPlan, context: SeasonContext) -> list[tuple[int, PlanWeek, SkeletonWeek]]:
    """The weeks of the plan that are weeks of the skeleton, with their place in the plan. A week
    that is not one is the business of ``check_weeks``."""
    by_start = {week.week_start: week for week in context.skeleton.weeks}
    return [
        (index, week, by_start[week.week_start])
        for index, week in enumerate(plan.weeks)
        if week.week_start in by_start
    ]


def check_weeks(plan: SeasonPlan, context: SeasonContext) -> list[Finding]:
    """The plan has exactly the weeks of the skeleton, in its order (an error): once for the
    number of weeks and once at the first week that is not the one that was asked for."""
    wanted = [week.week_start for week in context.skeleton.weeks]
    found = []
    if len(plan.weeks) != len(wanted):
        found.append(
            Finding(
                Severity.ERROR,
                "weeks_mismatch",
                f"The plan has {len(plan.weeks)} weeks; the season has {len(wanted)}, from "
                f"{_day(wanted[0]) if wanted else '-'} to {_day(wanted[-1]) if wanted else '-'}.",
                "weeks",
            )
        )
    for index, (given, expected) in enumerate(zip(plan.weeks, wanted, strict=False)):
        if given.week_start != expected:
            found.append(
                Finding(
                    Severity.ERROR,
                    "weeks_mismatch",
                    f"Week {index + 1} must be the week of {_day(expected)}.",
                    f"weeks[{index}].week_start",
                )
            )
            break
    return found


def check_sports(plan: SeasonPlan, context: SeasonContext) -> list[Finding]:
    """Minutes in a sport that the athlete did not choose (an error, once per sport and week, at
    the minutes of that sport)."""
    return [
        Finding(
            Severity.ERROR,
            "sport_not_selected",
            f"The week of {_day(week.week_start)} has {sport.value} minutes, but you did not "
            "choose that sport.",
            f"weeks[{index}].minutes.{sport.value}",
        )
        for index, week, _ in _matched(plan, context)
        for sport, amount in week.minutes
        if amount > 0 and sport not in context.sports
    ]


def check_minutes(plan: SeasonPlan, context: SeasonContext) -> list[Finding]:
    """The minutes of a week add up to the target of the skeleton, give or take
    ``WINDOW_PERCENT`` percent (an error, at the minutes of the week). A week with no target has
    no minutes."""
    found = []
    for index, week, planned in _matched(plan, context):
        low, high = window(planned.target_minutes)
        if low <= week.total <= high:
            continue
        found.append(
            Finding(
                Severity.ERROR,
                "minutes_outside_target",
                f"The week of {_day(week.week_start)} has {week.total} minutes; the skeleton "
                f"aims for {planned.target_minutes} (between {low} and {high}).",
                f"weeks[{index}].minutes",
            )
        )
    return found


def check_capacity(plan: SeasonPlan, context: SeasonContext) -> list[Finding]:
    """A week has more minutes than it offers (an error, at the minutes of the week). An absence
    offers nothing, the weekly budget caps the week."""
    return [
        Finding(
            Severity.ERROR,
            "minutes_above_capacity",
            f"The week of {_day(week.week_start)} has {week.total} minutes, but you can train "
            f"{planned.capacity_minutes} in it.",
            f"weeks[{index}].minutes",
        )
        for index, week, planned in _matched(plan, context)
        if week.total > planned.capacity_minutes
    ]


def check_key_sessions(plan: SeasonPlan, context: SeasonContext) -> list[Finding]:
    """The key sessions fit the week: a sport that has no minutes that week cannot have one (an
    error, at the session) and the sessions of a sport add up to no more than its minutes (an
    error, once per sport and week, at the key sessions)."""
    found = []
    for index, week, _ in _matched(plan, context):
        minutes = dict(week.minutes)
        used: dict[Sport, int] = {}
        for number, session in enumerate(week.key_sessions):
            if minutes.get(session.sport, 0) == 0:
                found.append(
                    Finding(
                        Severity.ERROR,
                        "key_session_sport_missing",
                        f"The week of {_day(week.week_start)} has a {session.sport.value} key "
                        f"session, but no {session.sport.value} minutes.",
                        f"weeks[{index}].key_sessions[{number}].sport",
                    )
                )
            else:
                used[session.sport] = used.get(session.sport, 0) + session.minutes
        for sport, spent in used.items():
            if spent > minutes[sport]:
                found.append(
                    Finding(
                        Severity.ERROR,
                        "key_sessions_too_long",
                        f"The {sport.value} key sessions of the week of "
                        f"{_day(week.week_start)} add up to {spent} minutes, more than its "
                        f"{minutes[sport]} {sport.value} minutes.",
                        f"weeks[{index}].key_sessions",
                    )
                )
    return found


def check_races(plan: SeasonPlan, context: SeasonContext) -> list[Finding]:
    """A week with a race has a key session that is the race (a warning, at the key sessions)."""
    return [
        Finding(
            Severity.WARNING,
            "race_week_without_race",
            f"The week of {_day(week.week_start)} has a race, but no key session of the kind "
            f"{SessionKind.RACE.value}.",
            f"weeks[{index}].key_sessions",
        )
        for index, week, planned in _matched(plan, context)
        if planned.races and not any(s.kind is SessionKind.RACE for s in week.key_sessions)
    ]


# In the order their findings are listed: the frame first, then what is in the weeks.
ALL_CHECKS: tuple[Check, ...] = (
    check_weeks,
    check_sports,
    check_minutes,
    check_capacity,
    check_key_sessions,
    check_races,
)


def validate_season(plan: SeasonPlan, context: SeasonContext) -> Report:
    """The report of all checks, in a stable order. The same plan and context always give the
    same report."""
    return Report(tuple(finding for check in ALL_CHECKS for finding in check(plan, context)))


def _day(day: date) -> str:
    return day.isoformat()
