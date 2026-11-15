"""Changing a week plan by hand: reading an edited plan and checking it.

An edited plan arrives as JSON in the format of ``planning.schema`` with one addition, an optional
``lineage`` per workout: which workout of the version it was made from this one is (see
``PlannedWorkout.lineage``), or ``null`` / left out for a workout that is new. It is read by the
strict parser like a plan of the coach; nothing of the input is repeated in a message.

``check`` runs the rules on it without storing anything, so that the page can show the findings
after every change. What is stored is a new draft version, made by ``revise``.
"""

from dataclasses import dataclass, replace
from datetime import date
from uuid import UUID

from accounts.models import User

from .context import build_context
from .generation import WeekNotPlannable, plannable_weeks
from .schema import PlanFormatError, Problem, WeekPlan, order_key, parse_week_plan
from .services import canonical
from .validation import Report, validate_week


@dataclass(frozen=True)
class EditedPlan:
    """A plan that was read, in the order it is stored in. ``order[i]`` is the place in the input of
    the workout that is the ``i``-th of the plan (the findings name the workouts by the latter)."""

    plan: WeekPlan
    order: tuple[int, ...]


@dataclass(frozen=True)
class Checked:
    report: Report
    order: tuple[int, ...]


def read_edited_plan(data: object, monday: date) -> EditedPlan:
    """The plan in ``data`` for the week of ``monday``, its workouts in the stored order (by day,
    then time of day, then as given) and with their lineages.

    Raises ``PlanFormatError`` with every problem found: those of the format, a plan for another
    week, a ``lineage`` that is no id and one that is used twice.
    """
    problems: list[Problem] = []
    lineages: list[UUID | None] = []
    cleaned = data
    if isinstance(data, dict) and isinstance(data.get("workouts"), list):
        stripped: list[object] = []
        for index, raw in enumerate(data["workouts"]):
            if isinstance(raw, dict) and "lineage" in raw:
                lineages.append(_lineage(raw["lineage"], f"workouts[{index}].lineage", problems))
                raw = {name: value for name, value in raw.items() if name != "lineage"}
            else:
                lineages.append(None)
            stripped.append(raw)
        cleaned = {**data, "workouts": stripped}
    try:
        plan = parse_week_plan(cleaned)
    except PlanFormatError as error:
        raise PlanFormatError((*problems, *error.problems)) from None
    if plan.week_start != monday:
        problems.append(
            Problem("week_start", f"The plan must be for the week that starts on {monday}.")
        )
    seen: set[UUID] = set()
    for index, lineage in enumerate(lineages):
        if lineage is not None and lineage in seen:
            problems.append(
                Problem(f"workouts[{index}].lineage", "A lineage can only be used once.")
            )
        elif lineage is not None:
            seen.add(lineage)
    if problems:
        raise PlanFormatError(tuple(problems))
    given = WeekPlan(
        plan.week_start,
        tuple(
            replace(workout, lineage=lineage)
            for workout, lineage in zip(plan.workouts, lineages, strict=True)
        ),
        plan.rationale,
    )
    order = tuple(sorted(range(len(given.workouts)), key=lambda i: order_key(given.workouts[i])))
    return EditedPlan(canonical(given), order)


def check(user: User, monday: date, data: object) -> Checked:
    """The report of the rules for the edited plan in ``data``, against what the user can do and
    has done *now*. Nothing is stored and nobody is asked.

    Raises ``WeekNotPlannable`` (the week is not one of ``plannable_weeks``) and
    ``PlanFormatError`` (``data`` is no plan, or not one for this week).
    """
    if monday not in plannable_weeks(user):
        raise WeekNotPlannable
    edited = read_edited_plan(data, monday)
    return Checked(validate_week(edited.plan, build_context(user, monday)), edited.order)


def _lineage(value: object, path: str, problems: list[Problem]) -> UUID | None:
    """The lineage in ``value`` (an id as text, or ``None`` for a workout that is new)."""
    if value is None:
        return None
    if isinstance(value, str):
        try:
            found = UUID(value)
        except ValueError:
            found = None
        if found is not None and str(found) == value:
            return found
    problems.append(Problem(path, "A lineage is an id or null."))
    return None
