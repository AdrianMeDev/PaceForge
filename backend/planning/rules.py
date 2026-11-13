"""The checks a week plan has to pass (PROJECT_PLAN 7.3). Pure functions on a plan and its context.

Every check returns its findings as a list and raises on nothing that a parsed plan can contain.
A finding has a stable ``code`` and a ``path`` into the plan (the same paths as the parser's
problems), and its message is a fixed text built from numbers, weekdays and fixed words only:
nothing the coach wrote (titles, notes) is repeated. An *error* makes a plan unfit to confirm, a
*warning* is for the user to weigh.

The limits are the constants below, in one place, so that they can be read and changed there.
"""

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from .context import PlanContext
from .schema import Sport, WeekPlan, Workout, ZoneSystem

# The segments of a workout may differ from its duration by this much before it is an error.
DURATION_TOLERANCE_SECONDS = 60

# The zone systems that make sense for a sport; swimming and strength have none.
SPORT_ZONE_SYSTEMS: dict[Sport, frozenset[ZoneSystem]] = {
    Sport.CYCLING: frozenset({ZoneSystem.POWER, ZoneSystem.HEART_RATE}),
    Sport.RUNNING: frozenset({ZoneSystem.PACE, ZoneSystem.HEART_RATE}),
    Sport.SWIMMING: frozenset(),
    Sport.STRENGTH: frozenset(),
}

_WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
_ABSENCES = {"illness": "an illness", "vacation": "a vacation"}


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True)
class Finding:
    severity: Severity
    code: str
    message: str
    path: str


Check = Callable[[WeekPlan, PlanContext], list[Finding]]


def check_inside_week(plan: WeekPlan, context: PlanContext) -> list[Finding]:
    """Every workout lies on a day of the week the plan is for."""
    _same_week(plan, context)
    return [
        Finding(
            Severity.ERROR,
            "outside_week",
            "The workout does not lie within the week of the plan.",
            f"workouts[{index}].day",
        )
        for index, workout in enumerate(plan.workouts)
        if context.offset(workout.day) is None
    ]


def check_segments_add_up(plan: WeekPlan, context: PlanContext) -> list[Finding]:
    """The interval structure of a workout takes as long as the workout says (within a minute)."""
    _same_week(plan, context)
    found = []
    for index, workout in enumerate(plan.workouts):
        if not workout.segments:
            continue
        total = sum(segment.seconds * segment.repeat for segment in workout.segments)
        stated = workout.duration_minutes * 60
        if abs(total - stated) > DURATION_TOLERANCE_SECONDS:
            found.append(
                Finding(
                    Severity.ERROR,
                    "segments_mismatch",
                    f"The segments add up to {total} seconds, the workout says {stated} seconds.",
                    f"workouts[{index}].segments",
                )
            )
    return found


def check_zone_systems(plan: WeekPlan, context: PlanContext) -> list[Finding]:
    """The zone system of every target fits the sport and the athlete has the threshold for it.

    Whether the zone exists in its system is settled by the parser. A system that does not fit
    the sport is reported once (not also as unavailable)."""
    _same_week(plan, context)
    found: list[Finding] = []
    for index, workout in enumerate(plan.workouts):
        path = f"workouts[{index}]"
        found += _zone_findings(workout.sport, workout.zone_system, context, f"{path}.zone_system")
        for number, segment in enumerate(workout.segments):
            found += _zone_findings(
                workout.sport,
                segment.zone_system,
                context,
                f"{path}.segments[{number}].zone_system",
            )
    return found


def check_day_capacity(plan: WeekPlan, context: PlanContext) -> list[Finding]:
    """The workouts of a day fit into the minutes the day offers, and none falls on an absence.

    On an ordinary day the first workout that makes the day too long is named; on a day of
    absence every workout is. Workouts outside the week are left to ``check_inside_week``."""
    _same_week(plan, context)
    by_day: dict[int, list[tuple[int, Workout]]] = {}
    for index, workout in enumerate(plan.workouts):
        offset = context.offset(workout.day)
        if offset is not None:
            by_day.setdefault(offset, []).append((index, workout))
    found: list[Finding] = []
    for offset in sorted(by_day):
        workouts = by_day[offset]
        weekday = _WEEKDAYS[offset]
        absence = context.absences[offset]
        if absence is not None:
            kind = _ABSENCES.get(absence, "a time of absence")
            found += [
                Finding(
                    Severity.ERROR,
                    "day_in_absence",
                    f"{weekday} lies within {kind}; no training is possible.",
                    f"workouts[{index}]",
                )
                for index, _ in workouts
            ]
            continue
        offered = context.minutes[offset]
        planned = sum(workout.duration_minutes for _, workout in workouts)
        running = 0
        for index, workout in workouts:
            running += workout.duration_minutes
            if running > offered:
                found.append(
                    Finding(
                        Severity.ERROR,
                        "day_over_capacity",
                        f"{weekday} offers {offered} minutes, the workouts of the day add up to "
                        f"{planned} minutes.",
                        f"workouts[{index}]",
                    )
                )
                break
    return found


def check_week_capacity(plan: WeekPlan, context: PlanContext) -> list[Finding]:
    """The week adds up to no more than the user offers, the weekly budget included."""
    _same_week(plan, context)
    planned = sum(
        workout.duration_minutes
        for workout in plan.workouts
        if context.offset(workout.day) is not None
    )
    if planned <= context.weekly_minutes:
        return []
    budget = context.weekly_budget
    capped = budget is not None and budget < sum(context.minutes)
    reason = f" with the weekly budget of {budget} minutes" if capped else ""
    return [
        Finding(
            Severity.ERROR,
            "week_over_capacity",
            f"The week adds up to {planned} minutes; the user offers "
            f"{context.weekly_minutes} minutes{reason}.",
            "workouts",
        )
    ]


# The checks of structure, zones and capacity, in the order their findings are listed.
BASIC_CHECKS: tuple[Check, ...] = (
    check_inside_week,
    check_segments_add_up,
    check_zone_systems,
    check_day_capacity,
    check_week_capacity,
)


def basic_checks(plan: WeekPlan, context: PlanContext) -> list[Finding]:
    """The findings of all checks of this module, check by check."""
    return [finding for check in BASIC_CHECKS for finding in check(plan, context)]


def _zone_findings(
    sport: Sport, system: ZoneSystem | None, context: PlanContext, path: str
) -> list[Finding]:
    if system is None:
        return []
    if system not in SPORT_ZONE_SYSTEMS[sport]:
        return [
            Finding(
                Severity.ERROR,
                "zone_system_not_for_sport",
                f"{_label(system)} zones do not apply to {sport.value}.",
                path,
            )
        ]
    if (sport, system) not in context.zone_systems:
        return [
            Finding(
                Severity.ERROR,
                "zone_system_unavailable",
                f"The athlete has no threshold for {_label(system).lower()} zones in "
                f"{sport.value}.",
                path,
            )
        ]
    return []


def _label(system: ZoneSystem) -> str:
    return {"power": "Power", "heart_rate": "Heart rate", "pace": "Pace"}[system.value]


def _same_week(plan: WeekPlan, context: PlanContext) -> None:
    if plan.week_start != context.week_start:
        raise ValueError("The context is for another week than the plan.")
