"""Changing a week plan by hand: reading an edited plan and checking it.

An edited plan arrives as JSON in the format of ``planning.schema`` with one addition, an optional
``lineage`` per workout: which workout of the version it was made from this one is (see
``PlannedWorkout.lineage``), or ``null`` / left out for a workout that is new. It is read by the
strict parser like a plan of the coach; nothing of the input is repeated in a message.

``check`` runs the rules on it without storing anything, so that the page can show the findings
after every change. What is stored is a new draft version, made by ``revise``: a confirmed plan is
never changed, a change is a new version of the week that says which one it was made from.
"""

from dataclasses import dataclass, replace
from datetime import date
from uuid import UUID

from accounts.models import User

from .context import build_context
from .generation import WeekNotPlannable, plannable_weeks
from .models import PlannedWorkout, WeeklyPlan
from .schema import PlanFormatError, Problem, WeekPlan, order_key, parse_week_plan
from .services import canonical, get, load, save_draft
from .validation import Report, validate_week

REASON = "Changed by hand"


class PlanNotRestorable(Exception):
    """Only a version that was replaced or discarded can be restored: a draft is a draft already,
    and a confirmed plan can be changed directly."""


class PlanNotRevisable(Exception):
    """Only a draft or a confirmed plan can be changed. An older version is restored first (it
    becomes a new draft), so that what is changed is what the user is working with."""


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
    seen: set[UUID] = set()
    for index, lineage in enumerate(lineages):
        if lineage is not None and lineage in seen:
            problems.append(
                Problem(f"workouts[{index}].lineage", "A lineage can only be used once.")
            )
        elif lineage is not None:
            seen.add(lineage)
    try:
        plan = parse_week_plan(cleaned)
    except PlanFormatError as error:
        raise PlanFormatError((*problems, *error.problems)) from None
    if plan.week_start != monday:
        problems.append(
            Problem("week_start", f"The plan must be for the week that starts on {monday}.")
        )
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


def revise(user: User, plan_id: UUID, data: object) -> WeeklyPlan:
    """Store the edited plan in ``data`` as the next version of the week of plan ``plan_id``, a
    draft that says it was made from that version (``reason`` "Changed by hand"). The rationale of
    the coach of that version is kept; the one in ``data`` is ignored.

    A workout with a ``lineage`` is the workout of that version with it, changed or moved; one
    without is new; a workout of that version that is not in ``data`` is taken out. The plan is
    stored as it is, also with errors in it (the user sees what is wrong; it cannot be confirmed).

    Raises ``PlanNotFound`` (no such plan of the user), ``PlanNotRevisable``, ``WeekNotPlannable``
    and ``PlanFormatError`` (``data`` is no plan for the week, or a lineage is not one of the
    workouts of the plan that is changed); in each case nothing is stored.
    """
    parent = get(user, plan_id)
    if parent.status not in (WeeklyPlan.Status.DRAFT, WeeklyPlan.Status.CONFIRMED):
        raise PlanNotRevisable
    if parent.week_start not in plannable_weeks(user):
        raise WeekNotPlannable
    edited = read_edited_plan(data, parent.week_start)
    own = set(
        PlannedWorkout.objects.for_user(user).filter(plan=parent).values_list("lineage", flat=True)
    )
    strangers = [
        Problem(
            f"workouts[{edited.order[place]}].lineage",
            "This workout is not in the plan that is changed.",
        )
        for place, found in enumerate(edited.plan.workouts)
        if found.lineage is not None and found.lineage not in own
    ]
    if strangers:
        raise PlanFormatError(tuple(sorted(strangers, key=_by_index)))
    plan = replace(edited.plan, rationale=parent.rationale)
    return save_draft(user, plan, reason=REASON, parent=parent.pk)


def restore(user: User, plan_id: UUID) -> WeeklyPlan:
    """Bring back a version of a week that was replaced or discarded, as the next version: a draft
    with the same workouts (and lineages) and the same rationale, ``parent`` the version it was
    restored from and a ``reason`` that says so. It is checked again with what the user can do now
    when it is shown, and it is confirmed (and sent) like any other draft; nothing else changes.

    Raises ``PlanNotFound``, ``PlanNotRestorable`` and ``WeekNotPlannable`` (the week is not one of
    ``plannable_weeks``); in each case nothing is stored.
    """
    old = get(user, plan_id)
    if old.status not in (WeeklyPlan.Status.SUPERSEDED, WeeklyPlan.Status.DISCARDED):
        raise PlanNotRestorable
    if old.week_start not in plannable_weeks(user):
        raise WeekNotPlannable
    return save_draft(
        user, load(user, old.pk), reason=f"Restored from version {old.version}", parent=old.pk
    )


def _by_index(problem: Problem) -> int:
    return int(problem.path.split("[")[1].split("]")[0])


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
