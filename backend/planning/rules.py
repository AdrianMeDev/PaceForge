"""The checks a week plan has to pass (PROJECT_PLAN 7.3). Pure functions on a plan and its context.

Every check returns its findings as a list and raises on nothing that a parsed plan can contain.
A finding has a stable ``code`` and a ``path`` into the plan (the same paths as the parser's
problems), and its message is a fixed text built from numbers, weekdays and fixed words only:
nothing the coach wrote (titles, notes) is repeated. An *error* makes a plan unfit to confirm, a
*warning* is for the user to weigh.

The fixed limits are the constants below, in one place, so that they can be read and changed there.
The limits that depend on how hard the athlete wants to train (hard days, progression) come with
the context (``context.limits``, see ``availability.intensity``).
"""

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from fractions import Fraction

from .context import PlanContext
from .schema import Goal, Slot, Sport, WeekPlan, Workout, ZoneSystem

# The segments of a workout may differ from its duration by this much before it is an error.
DURATION_TOLERANCE_SECONDS = 60

# The zone systems that make sense for a sport; swimming and strength have none.
SPORT_ZONE_SYSTEMS: dict[Sport, frozenset[ZoneSystem]] = {
    Sport.CYCLING: frozenset({ZoneSystem.POWER, ZoneSystem.HEART_RATE}),
    Sport.RUNNING: frozenset({ZoneSystem.PACE, ZoneSystem.HEART_RATE}),
    Sport.SWIMMING: frozenset(),
    Sport.STRENGTH: frozenset(),
}

# The rhythm of a week. A workout is hard from this zone on (whatever the zone system) or if its
# goal is threshold or VO2max; it is easy up to this zone or without any zone. How many hard days
# a week may have is a limit of the athlete's intensity level.
HARD_FROM_ZONE = 4
EASY_UP_TO_ZONE = 2
MAX_WORKOUTS_PER_DAY = 2
# How much of the athlete's own "typical week" counts as the reference, in percent. The reference
# is the higher of this and the average of the recent weeks, so that someone coming back from a
# break is not held to the few weeks since. 100 takes the athlete at their word; a lower number
# (70, say) makes the first weeks back more careful.
TYPICAL_VOLUME_PERCENT = 100

_WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
_ABSENCES = {"illness": "an illness", "vacation": "a vacation"}


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


class Intensity(StrEnum):
    EASY = "easy"
    MODERATE = "moderate"
    HARD = "hard"


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


def intensity_of(workout: Workout) -> Intensity:
    """How hard a workout is: hard for the goals threshold and VO2max or from zone 4 on (the
    highest zone of the workout and its segments), easy up to zone 2 or without a zone."""
    if workout.goal in (Goal.THRESHOLD, Goal.VO2MAX):
        return Intensity.HARD
    zones = [segment.zone for segment in workout.segments if segment.zone is not None]
    if workout.zone is not None:
        zones.append(workout.zone)
    top = max(zones, default=None)
    if top is not None and top >= HARD_FROM_ZONE:
        return Intensity.HARD
    if top is None or top <= EASY_UP_TO_ZONE:
        return Intensity.EASY
    return Intensity.MODERATE


def check_hard_days(plan: WeekPlan, context: PlanContext) -> list[Finding]:
    """No more days with a hard workout in a week than the athlete's limit allows."""
    _same_week(plan, context)
    hard = _hard_workouts_by_day(plan, context)
    allowed = context.limits.max_hard_days
    if len(hard) <= allowed:
        return []
    days = "1 hard day" if len(hard) == 1 else f"{len(hard)} hard days"
    return [
        Finding(
            Severity.ERROR,
            "too_many_hard_days",
            f"The week has {days}; your intensity settings allow at most {allowed}.",
            "workouts",
        )
    ]


def check_hard_days_in_a_row(plan: WeekPlan, context: PlanContext) -> list[Finding]:
    """A hard day directly after a hard day leaves no time to recover (a warning)."""
    _same_week(plan, context)
    hard = _hard_workouts_by_day(plan, context)
    return [
        Finding(
            Severity.WARNING,
            "hard_days_in_a_row",
            f"{_WEEKDAYS[offset]} is a hard day directly after another hard day.",
            f"workouts[{hard[offset][0][0]}]",
        )
        for offset in sorted(hard)
        if offset - 1 in hard
    ]


def check_a_free_day(plan: WeekPlan, context: PlanContext) -> list[Finding]:
    """At least one day of the week without a workout (a warning)."""
    _same_week(plan, context)
    days = _workouts_by_day(plan, context)
    if len(days) < 7:
        return []
    return [
        Finding(
            Severity.WARNING,
            "no_free_day",
            "Every day of the week has a workout; a day to rest is missing.",
            "workouts",
        )
    ]


def check_workouts_per_day(plan: WeekPlan, context: PlanContext) -> list[Finding]:
    """No more than ``MAX_WORKOUTS_PER_DAY`` workouts on a day (a warning, named once per day)."""
    _same_week(plan, context)
    found = []
    for offset, workouts in sorted(_workouts_by_day(plan, context).items()):
        if len(workouts) > MAX_WORKOUTS_PER_DAY:
            found.append(
                Finding(
                    Severity.WARNING,
                    "many_workouts_in_a_day",
                    f"{_WEEKDAYS[offset]} has {len(workouts)} workouts; more than "
                    f"{MAX_WORKOUTS_PER_DAY} in a day is a lot.",
                    f"workouts[{workouts[MAX_WORKOUTS_PER_DAY][0]}]",
                )
            )
    return found


def check_duplicates(plan: WeekPlan, context: PlanContext) -> list[Finding]:
    """The same workout twice on a day (same sport, goal and duration) is probably a mistake. A
    warning for every repeat after the first."""
    _same_week(plan, context)
    found = []
    for offset, workouts in sorted(_workouts_by_day(plan, context).items()):
        seen: set[tuple[Sport, Goal, int]] = set()
        for index, workout in workouts:
            key = (workout.sport, workout.goal, workout.duration_minutes)
            if key in seen:
                found.append(
                    Finding(
                        Severity.WARNING,
                        "duplicate_workout",
                        f"{_WEEKDAYS[offset]} has the same workout twice "
                        "(sport, goal and duration).",
                        f"workouts[{index}]",
                    )
                )
            seen.add(key)
    return found


def check_progression(plan: WeekPlan, context: PlanContext) -> list[Finding]:
    """The planned minutes stay within a plausible step from what the athlete has been doing.

    The reference is the higher of the average of ``context.recent_weeks`` and the typical week of
    the athlete (``TYPICAL_VOLUME_PERCENT`` of it). Above the warning limit of ``context.limits``
    (percent of the reference) is a warning, above its error limit an error. Without a reference,
    or with a reference of no minutes, nothing is checked: a number is not made up."""
    _same_week(plan, context)
    reference = _reference_week(context)
    if reference is None:
        return []
    source, per_week = reference
    planned = sum(
        workout.duration_minutes
        for workout in plan.workouts
        if context.offset(workout.day) is not None
    )
    # planned / per_week > percent / 100, exactly (no rounding of the reference)
    scaled = Fraction(planned * 100) / per_week
    if scaled > context.limits.progression_error_percent:
        severity, code = Severity.ERROR, "volume_jump"
    elif scaled > context.limits.progression_warning_percent:
        severity, code = Severity.WARNING, "volume_increase"
    else:
        return []
    return [
        Finding(
            severity,
            code,
            f"The week adds up to {planned} minutes, {round(scaled)} % of {source}.",
            "workouts",
        )
    ]


def _reference_week(context: PlanContext) -> tuple[str, Fraction] | None:
    """The reference minutes per week, with the words that say where it comes from: the higher of
    the recent average and the typical week. ``None`` if neither is more than no minutes."""
    options: list[tuple[str, Fraction]] = []
    weeks = context.recent_weeks
    if weeks and sum(weeks) > 0:
        average = Fraction(sum(weeks), len(weeks))
        options.append(
            (f"the average of {round(average)} minutes of the last {len(weeks)} week(s)", average)
        )
    typical = context.typical_weekly_minutes
    if typical:
        share = "" if TYPICAL_VOLUME_PERCENT == 100 else f"{TYPICAL_VOLUME_PERCENT} % of "
        options.append(
            (
                f"{share}your typical week of {typical} minutes",
                Fraction(typical * TYPICAL_VOLUME_PERCENT, 100),
            )
        )
    # The recent weeks come first, so that they name the source when both are equal.
    return max(options, key=lambda option: option[1], default=None)


def check_sports(plan: WeekPlan, context: PlanContext) -> list[Finding]:
    """Every workout is in a sport the athlete wants in a plan (an error)."""
    _same_week(plan, context)
    return [
        Finding(
            Severity.ERROR,
            "sport_not_selected",
            f"{_WEEKDAYS[offset]} has a {workout.sport.value} workout, "
            "which is not one of the sports you chose.",
            f"workouts[{index}].sport",
        )
        for offset, workouts in sorted(_workouts_by_day(plan, context).items())
        for index, workout in workouts
        if workout.sport not in context.sports
    ]


def check_stretching(plan: WeekPlan, context: PlanContext) -> list[Finding]:
    """Stretching is only added if the athlete wants it (an error). It is never a workout of its
    own and counts for no minutes: nothing else looks at it."""
    _same_week(plan, context)
    if context.stretching:
        return []
    return [
        Finding(
            Severity.ERROR,
            "stretching_not_wanted",
            f"{_WEEKDAYS[offset]} has stretching added, but you did not ask for stretching.",
            f"workouts[{index}].stretching_minutes",
        )
        for offset, workouts in sorted(_workouts_by_day(plan, context).items())
        for index, workout in workouts
        if workout.stretching_minutes > 0
    ]


def check_times_of_day(plan: WeekPlan, context: PlanContext) -> list[Finding]:
    """Several workouts on a day need a time of day each, and no two share one.

    The second workout in the same part of the day is an error (named at that workout); a day
    with several workouts of which one has no time of day is a warning, named once per day at the
    first workout without one."""
    _same_week(plan, context)
    found: list[Finding] = []
    for offset, workouts in sorted(_workouts_by_day(plan, context).items()):
        if len(workouts) < 2:
            continue
        taken: set[Slot] = set()
        for index, workout in workouts:
            if workout.slot is None:
                continue
            if workout.slot in taken:
                found.append(
                    Finding(
                        Severity.ERROR,
                        "same_slot",
                        f"{_WEEKDAYS[offset]} has two workouts in the {workout.slot.value}.",
                        f"workouts[{index}].slot",
                    )
                )
            taken.add(workout.slot)
        without = [index for index, workout in workouts if workout.slot is None]
        if without:
            found.append(
                Finding(
                    Severity.WARNING,
                    "slot_missing",
                    f"{_WEEKDAYS[offset]} has {len(workouts)} workouts; say for each when it is "
                    "(morning, afternoon or evening).",
                    f"workouts[{without[0]}].slot",
                )
            )
    return found


# The checks of structure, zones and capacity, in the order their findings are listed.
BASIC_CHECKS: tuple[Check, ...] = (
    check_inside_week,
    check_segments_add_up,
    check_zone_systems,
    check_day_capacity,
    check_week_capacity,
    check_sports,
    check_stretching,
)


# The checks of rhythm and progression, listed after the basic ones.
RHYTHM_CHECKS: tuple[Check, ...] = (
    check_hard_days,
    check_hard_days_in_a_row,
    check_a_free_day,
    check_workouts_per_day,
    check_duplicates,
    check_progression,
    check_times_of_day,
)

ALL_CHECKS: tuple[Check, ...] = BASIC_CHECKS + RHYTHM_CHECKS


def basic_checks(plan: WeekPlan, context: PlanContext) -> list[Finding]:
    """The findings of the checks of structure, zones and capacity, check by check."""
    return [finding for check in BASIC_CHECKS for finding in check(plan, context)]


def _workouts_by_day(plan: WeekPlan, context: PlanContext) -> dict[int, list[tuple[int, Workout]]]:
    """The workouts of the week by their place in it, each with its place in the plan's list.
    Workouts outside the week are left out."""
    by_day: dict[int, list[tuple[int, Workout]]] = {}
    for index, workout in enumerate(plan.workouts):
        offset = context.offset(workout.day)
        if offset is not None:
            by_day.setdefault(offset, []).append((index, workout))
    return by_day


def _hard_workouts_by_day(
    plan: WeekPlan, context: PlanContext
) -> dict[int, list[tuple[int, Workout]]]:
    hard = {}
    for offset, workouts in _workouts_by_day(plan, context).items():
        found = [(i, w) for i, w in workouts if intensity_of(w) is Intensity.HARD]
        if found:
            hard[offset] = found
    return hard


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
