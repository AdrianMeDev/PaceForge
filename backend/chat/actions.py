"""What the coach may do to the plan of a week from the chat, and the code that does it.

The coach never writes the plan: it names actions (``move_workout``, ``skip_workout`` …) with
arguments, ``read_actions`` reads them strictly and ``apply`` changes the plan, workout by workout.
Nothing in the past is changed, a workout is named by its lineage (the id the coach was given), and
everything that is wrong is refused before anything is stored. The sentences that tell what changed
are made here, from what was done: never from the words of the coach.

An action is a plain change of the plan; whether the plan is still good is the business of the
checks (``planning.validation``), which run on the draft that is stored from it.
"""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date, timedelta
from typing import Any
from uuid import UUID

from planning.schema import DURATION_MAX, Problem, Slot, Sport, WeekPlan, Workout

MAX_ACTIONS = 10
# The shortest workout the chat makes; a shorter one is a removed one.
MIN_MINUTES = 10
PERCENT_MIN = 5
PERCENT_MAX = 50

TOOLS = ("move_workout", "skip_workout", "swap_sport", "shorten_workout", "reduce_week", "free_day")
_DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_NAMES = {
    Sport.RUNNING: "Run",
    Sport.CYCLING: "Ride",
    Sport.SWIMMING: "Swim",
    Sport.STRENGTH: "Strength",
}


class ActionFormatError(Exception):
    """The actions cannot be read or cannot be applied. ``problems`` has every one found."""

    def __init__(self, problems: tuple[Problem, ...]) -> None:
        super().__init__(f"The actions have {len(problems)} problem(s).")
        self.problems = problems


@dataclass(frozen=True)
class MoveWorkout:
    id: UUID
    day: date
    slot: Slot | None = None


@dataclass(frozen=True)
class SkipWorkout:
    id: UUID


@dataclass(frozen=True)
class SwapSport:
    id: UUID
    sport: Sport
    minutes: int | None = None


@dataclass(frozen=True)
class ShortenWorkout:
    id: UUID
    minutes: int


@dataclass(frozen=True)
class ReduceWeek:
    percent: int


@dataclass(frozen=True)
class FreeDay:
    day: date


Action = MoveWorkout | SkipWorkout | SwapSport | ShortenWorkout | ReduceWeek | FreeDay

_FIELDS: dict[str, set[str]] = {
    "move_workout": {"tool", "id", "day", "slot"},
    "skip_workout": {"tool", "id"},
    "swap_sport": {"tool", "id", "sport", "minutes"},
    "shorten_workout": {"tool", "id", "minutes"},
    "reduce_week": {"tool", "percent"},
    "free_day": {"tool", "day"},
}
_REQUIRED: dict[str, set[str]] = {
    "move_workout": {"id", "day"},
    "skip_workout": {"id"},
    "swap_sport": {"id", "sport"},
    "shorten_workout": {"id", "minutes"},
    "reduce_week": {"percent"},
    "free_day": {"day"},
}


def read_actions(data: object, plan: WeekPlan, today: date) -> tuple[Action, ...]:
    """The actions in ``data`` (a list of objects with a ``tool``), checked against ``plan`` and
    ``today``. Raises ``ActionFormatError`` with every problem found."""
    if not isinstance(data, list):
        raise ActionFormatError((Problem("actions", "The actions are not a list."),))
    if len(data) > MAX_ACTIONS:
        raise ActionFormatError((Problem("actions", f"At most {MAX_ACTIONS} actions at once."),))
    problems: list[Problem] = []
    actions: list[Action] = []
    for index, item in enumerate(data):
        found = _read_one(item, f"actions[{index}]", plan, today, problems)
        if found is not None:
            actions.append(found)
    if problems:
        raise ActionFormatError(tuple(problems))
    return tuple(actions)


def _read_one(
    item: object, path: str, plan: WeekPlan, today: date, problems: list[Problem]
) -> Action | None:
    if not isinstance(item, dict):
        problems.append(Problem(path, "An action is an object."))
        return None
    tool = item.get("tool")
    if not isinstance(tool, str) or tool not in TOOLS:
        problems.append(Problem(f"{path}.tool", "This is not one of the tools."))
        return None
    before = len(problems)
    for name in sorted(set(item) - _FIELDS[tool]):
        problems.append(Problem(f"{path}.{name}", "This field is not part of the tool."))
    for name in sorted(_REQUIRED[tool] - set(item)):
        problems.append(Problem(f"{path}.{name}", "This field is missing."))
    if len(problems) > before:
        return None
    match tool:
        case "move_workout":
            workout = _workout(item["id"], f"{path}.id", plan, today, problems)
            day = _day(item["day"], f"{path}.day", plan, today, problems)
            slot = _slot(item.get("slot"), f"{path}.slot", problems)
            if workout is None or day is None or len(problems) > before:
                return None
            return MoveWorkout(workout.lineage, day, slot)  # type: ignore[arg-type]
        case "skip_workout":
            workout = _workout(item["id"], f"{path}.id", plan, today, problems)
            return None if workout is None else SkipWorkout(workout.lineage)  # type: ignore[arg-type]
        case "swap_sport":
            workout = _workout(item["id"], f"{path}.id", plan, today, problems)
            sport = _sport(item["sport"], f"{path}.sport", problems)
            minutes = _minutes(item.get("minutes"), f"{path}.minutes", problems, optional=True)
            if workout is None or sport is None or len(problems) > before:
                return None
            return SwapSport(workout.lineage, sport, minutes)  # type: ignore[arg-type]
        case "shorten_workout":
            workout = _workout(item["id"], f"{path}.id", plan, today, problems)
            minutes = _minutes(item["minutes"], f"{path}.minutes", problems)
            if workout is not None and minutes is not None:
                if minutes >= workout.duration_minutes:
                    problems.append(Problem(f"{path}.minutes", "This is not shorter."))
            if workout is None or minutes is None or len(problems) > before:
                return None
            return ShortenWorkout(workout.lineage, minutes)  # type: ignore[arg-type]
        case "reduce_week":
            percent = item["percent"]
            if (
                not isinstance(percent, int)
                or isinstance(percent, bool)
                or not PERCENT_MIN <= percent <= PERCENT_MAX
            ):
                problems.append(
                    Problem(
                        f"{path}.percent", f"A whole number from {PERCENT_MIN} to {PERCENT_MAX}."
                    )
                )
                return None
            return ReduceWeek(percent)
        case _:  # free_day
            day = _day(item["day"], f"{path}.day", plan, today, problems)
            return None if day is None else FreeDay(day)


def _workout(
    value: object, path: str, plan: WeekPlan, today: date, problems: list[Problem]
) -> Workout | None:
    try:
        wanted = UUID(value) if isinstance(value, str) else None
    except ValueError:
        wanted = None
    found = next((w for w in plan.workouts if wanted is not None and w.lineage == wanted), None)
    if found is None:
        problems.append(Problem(path, "This is not a workout of the plan."))
        return None
    if found.day < today:
        problems.append(Problem(path, "This workout is in the past and cannot be changed."))
        return None
    return found


def _day(
    value: object, path: str, plan: WeekPlan, today: date, problems: list[Problem]
) -> date | None:
    try:
        day = date.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        day = None
    if day is None:
        problems.append(Problem(path, "This is not a date (YYYY-MM-DD)."))
        return None
    if not plan.week_start <= day <= plan.week_start + timedelta(days=6):
        problems.append(Problem(path, "This day is not in the week of the plan."))
        return None
    if day < today:
        problems.append(Problem(path, "This day is in the past."))
        return None
    return day


def _slot(value: object, path: str, problems: list[Problem]) -> Slot | None:
    if value is None:
        return None
    try:
        return Slot(value)  # type: ignore[arg-type]
    except ValueError:
        problems.append(Problem(path, "Morning, afternoon, evening or nothing."))
        return None


def _sport(value: object, path: str, problems: list[Problem]) -> Sport | None:
    try:
        return Sport(value)  # type: ignore[arg-type]
    except ValueError:
        problems.append(Problem(path, "Running, cycling, swimming or strength."))
        return None


def _minutes(
    value: object, path: str, problems: list[Problem], optional: bool = False
) -> int | None:
    if value is None and optional:
        return None
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or not MIN_MINUTES <= value <= DURATION_MAX
    ):
        problems.append(Problem(path, f"A whole number of minutes, at least {MIN_MINUTES}."))
        return None
    return value


def apply(
    plan: WeekPlan, actions: Sequence[Action], today: date
) -> tuple[WeekPlan, tuple[str, ...]]:
    """``plan`` with ``actions`` done one after the other, and a sentence for each change. What is
    before ``today`` is never touched.

    Raises ``ActionFormatError`` if an action names a workout that an earlier one took out; the
    plan is not changed (it is a value) and nothing is stored."""
    workouts = list(plan.workouts)
    changes: list[str] = []
    for index, action in enumerate(actions):
        match action:
            case ReduceWeek(percent):
                changes.extend(_reduce(workouts, percent, today))
            case FreeDay(day):
                changes.extend(_free(workouts, day))
            case _:
                place = next(
                    (n for n, w in enumerate(workouts) if w.lineage == action.id),
                    None,
                )
                if place is None:
                    raise ActionFormatError(
                        (
                            Problem(
                                f"actions[{index}].id",
                                "This workout is not in the plan any more.",
                            ),
                        )
                    )
                changes.append(_one(workouts, place, action))
    return replace(plan, workouts=tuple(workouts)), tuple(changes)


def _label(workout: Workout) -> str:
    name, day = _NAMES[workout.sport], _DAYS[workout.day.weekday()]
    return f"{name} on {day} ({workout.duration_minutes} min)"


def _one(workouts: list[Workout], place: int, action: Action) -> str:
    workout = workouts[place]
    label = _label(workout)
    match action:
        case MoveWorkout(_, day, slot):
            workouts[place] = replace(workout, day=day, slot=slot or workout.slot)
            return f"{label} moved to {_DAYS[day.weekday()]}"
        case SkipWorkout():
            del workouts[place]
            return f"{label} removed"
        case SwapSport(_, sport, minutes):
            minutes = minutes or workout.duration_minutes
            workouts[place] = _simple(workout, sport=sport, minutes=minutes)
            return f"{label} replaced by {_NAMES[sport]} ({minutes} min)"
        case ShortenWorkout(_, minutes):
            workouts[place] = _simple(workout, minutes=minutes)
            return f"{label} shortened to {minutes} min"
    raise AssertionError("unreachable")


def _simple(workout: Workout, sport: Sport | None = None, minutes: int | None = None) -> Workout:
    """The workout with another sport or length. Its steps and exercises were made for the old
    one, so they go: it becomes one steady session; a note about the old workout goes too."""
    changed_sport = sport is not None and sport is not workout.sport
    return replace(
        workout,
        sport=sport or workout.sport,
        duration_minutes=minutes or workout.duration_minutes,
        segments=(),
        exercises=workout.exercises if not changed_sport and sport is None else (),
        zone_system=None if changed_sport else workout.zone_system,
        zone=None if changed_sport else workout.zone,
        notes="" if changed_sport else workout.notes,
    )


def _reduce(workouts: list[Workout], percent: int, today: date) -> list[str]:
    shortened = 0
    for place, workout in enumerate(workouts):
        if workout.day < today:
            continue
        minutes = max(MIN_MINUTES, round(workout.duration_minutes * (100 - percent) / 100))
        if minutes < workout.duration_minutes:
            workouts[place] = _simple(workout, minutes=minutes)
            shortened += 1
    word = "workout" if shortened == 1 else "workouts"
    return [f"Week reduced by {percent} %: {shortened} {word} shortened"]


def _free(workouts: list[Workout], day: date) -> list[str]:
    kept = [w for w in workouts if w.day != day]
    removed = len(workouts) - len(kept)
    workouts[:] = kept
    word = "workout" if removed == 1 else "workouts"
    return [f"{_DAYS[day.weekday()]} freed: {removed} {word} removed"]


def as_data(actions: Sequence[Action]) -> list[dict[str, Any]]:
    """The actions as plain data, for a log or a test."""
    return [{"tool": _tool(action), **vars(action)} for action in actions]


def _tool(action: Action) -> str:
    return {
        MoveWorkout: "move_workout",
        SkipWorkout: "skip_workout",
        SwapSport: "swap_sport",
        ShortenWorkout: "shorten_workout",
        ReduceWeek: "reduce_week",
        FreeDay: "free_day",
    }[type(action)]
