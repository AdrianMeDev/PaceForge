"""Storing, revising and confirming week plans.

Every function acts on the plans of the user it is given and on nothing else: another user's plan
does not exist as far as these functions are concerned (``PlanNotFound``). Plans are referred to
by id, as an API will.

A plan is a *draft* until it is confirmed. Drafts may be stored with training-rule errors (the
user is shown what is wrong), but every workout must lie within the plan week. A plan with an
error is never confirmed, and confirming checks again with the data of that moment. A confirmed
plan, a superseded one and a discarded one are never changed: a change is a new version of the
week, which says which version it replaces and why.
"""

import uuid
from dataclasses import replace
from datetime import datetime
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from accounts.models import User
from reviews.services import carry_over

from .context import build_context
from .models import NOTE_MAX, REASON_MAX, PlannedWorkout, WeeklyPlan
from .schema import PlanFormatError, Problem, WeekPlan, order_key, parse_week_plan, workout_to_json
from .validation import Report, validate_week

Status = WeeklyPlan.Status


class PlanNotFound(Exception):
    """The user has no plan with this id."""


class PlanStateError(Exception):
    """The plan is not in a state that allows this: only a draft can be confirmed or discarded."""


class PlanNotConfirmable(Exception):
    """The plan has errors and cannot be confirmed. ``report`` says which."""

    def __init__(self, report: Report) -> None:
        super().__init__("The plan has errors and cannot be confirmed.")
        self.report = report


def _now() -> datetime:
    return timezone.now()


def canonical(plan: WeekPlan) -> WeekPlan:
    """The plan with its workouts in the order they are stored and read back: by day, within a
    day by time of day (a workout without one last) and otherwise in the order given. Validate
    this form, so that the paths of the findings (such as ``workouts[2]``) are the places in
    what is stored."""
    return WeekPlan(
        plan.week_start,
        tuple(sorted(plan.workouts, key=order_key)),
        plan.rationale,
    )


def outside_week_problems(plan: WeekPlan) -> tuple[Problem, ...]:
    """Storage requires every workout to lie in the plan's Monday-to-Sunday week.

    Paths refer to the order given, so edited input can report the offending workout.
    """
    return tuple(
        Problem(f"workouts[{index}].day", "The workout does not lie within the week of the plan.")
        for index, workout in enumerate(plan.workouts)
        if not 0 <= (workout.day - plan.week_start).days < 7
    )


def save_draft(
    user: User,
    week_plan: WeekPlan,
    reason: str = "",
    parent: UUID | None = None,
    note: str = "",
) -> WeeklyPlan:
    """Store ``week_plan`` as the next version of its week, as a draft.

    ``parent`` is the version it replaces (it must be of the same week); ``reason`` is a short
    plain line saying why; ``note`` is what the athlete wrote about the week when asking for it
    (see ``clean_note``). Nothing is stored if anything goes wrong. The plan is stored as it is,
    even if training-rule validation has things to say about it. Out-of-week workouts raise
    ``PlanFormatError`` before anything is stored."""
    reason = _clean_reason(reason)
    note = clean_note(note)
    if problems := outside_week_problems(week_plan):
        raise PlanFormatError(problems)
    week_plan = canonical(week_plan)  # stored and read back in the order of the day
    if parent is not None:
        replaced = get(user, parent)
        if replaced.week_start != week_plan.week_start:
            raise ValueError("A version replaces a version of the same week.")
    for attempt in (1, 2):
        try:
            with transaction.atomic():
                return _store(user, week_plan, reason, parent, note)
        except IntegrityError:
            # Another request took the version number first; the next round counts again.
            if attempt == 2:
                raise
    raise AssertionError("unreachable")


def get(user: User, plan_id: UUID) -> WeeklyPlan:
    plan = WeeklyPlan.objects.for_user(user).filter(pk=plan_id).first()
    if plan is None:
        raise PlanNotFound
    return plan


def load(user: User, plan_id: UUID) -> WeekPlan:
    """The stored plan in the format of ``planning.schema``, workouts by day and position.

    The stored data goes through the strict parser again: what is read back is always valid."""
    plan = get(user, plan_id)
    rows = list(
        PlannedWorkout.objects.for_user(user)
        .filter(plan=plan)
        .order_by("day", "position", "id")
        .values(
            "lineage",
            "day",
            "sport",
            "title",
            "goal",
            "duration_minutes",
            "zone_system",
            "zone",
            "notes",
            "segments",
            "exercises",
            "slot",
            "stretching_minutes",
        )
    )
    parsed = parse_week_plan(
        {
            "week_start": plan.week_start.isoformat(),
            "rationale": plan.rationale,
            "workouts": [
                {
                    **{name: value for name, value in row.items() if name != "lineage"},
                    "day": row["day"].isoformat(),
                    "zone_system": row["zone_system"] or None,
                    "slot": row["slot"] or None,
                }
                for row in rows
            ],
        }
    )
    # The lineage is not part of the format: it is put back on the workouts, which the parser
    # returns in the order it was given them.
    assert len(parsed.workouts) == len(rows)
    return WeekPlan(
        parsed.week_start,
        tuple(
            replace(workout, lineage=row["lineage"])
            for workout, row in zip(parsed.workouts, rows, strict=True)
        ),
        parsed.rationale,
    )


def validate(user: User, plan_id: UUID) -> Report:
    """The report of the stored plan against what the user can do and has done *now*."""
    week_plan = load(user, plan_id)
    return validate_week(week_plan, build_context(user, week_plan.week_start))


def confirm(user: User, plan_id: UUID) -> WeeklyPlan:
    """Confirm a draft. The plan is validated again; with any error it is refused
    (``PlanNotConfirmable``) and nothing changes. The version of the week that was confirmed
    before becomes ``superseded``, and what the user said about its workouts in the week review
    moves to the workouts of the new version that are the same training (``carry_over``). Only a
    draft can be confirmed (``PlanStateError``)."""
    with transaction.atomic():
        plan = _lock_the_week(user, plan_id)
        if plan.status != Status.DRAFT:
            raise PlanStateError
        report = validate(user, plan_id)
        if not report.valid:
            raise PlanNotConfirmable(report)
        replaced = list(
            WeeklyPlan.objects.for_user(user).filter(
                week_start=plan.week_start, status=Status.CONFIRMED
            )
        )
        WeeklyPlan.objects.for_user(user).filter(pk__in=[found.pk for found in replaced]).update(
            status=Status.SUPERSEDED
        )
        plan.status = Status.CONFIRMED
        plan.confirmed_at = _now()
        plan.save(update_fields=["status", "confirmed_at"])
        for found in replaced:  # at most one: what the user said about its workouts moves along
            carry_over(user, found, plan)
        return plan


def discard(user: User, plan_id: UUID) -> WeeklyPlan:
    """Throw a draft away. Only a draft can be discarded (``PlanStateError``)."""
    with transaction.atomic():
        plan = _lock_the_week(user, plan_id)
        if plan.status != Status.DRAFT:
            raise PlanStateError
        plan.status = Status.DISCARDED
        plan.save(update_fields=["status"])
        return plan


def _lock_the_week(user: User, plan_id: UUID) -> WeeklyPlan:
    """Lock every version of the plan's week, so that two confirmations of the same week queue up
    instead of both finding the week free, and return the plan as it is now."""
    week_start = get(user, plan_id).week_start
    versions = list(
        WeeklyPlan.objects.for_user(user)
        .filter(week_start=week_start)
        .select_for_update()
        .order_by("pk")
    )
    for plan in versions:
        if plan.pk == plan_id:
            return plan
    raise PlanNotFound  # deleted meanwhile


def _store(
    user: User, week_plan: WeekPlan, reason: str, parent: UUID | None, note: str
) -> WeeklyPlan:
    last = (
        WeeklyPlan.objects.for_user(user)
        .filter(week_start=week_plan.week_start)
        .order_by("-version")
        .values_list("version", flat=True)
        .first()
    )
    plan = WeeklyPlan.objects.create(
        owner=user,
        week_start=week_plan.week_start,
        version=(last or 0) + 1,
        parent_id=parent,
        reason=reason,
        rationale=week_plan.rationale,
        note=note,
    )
    positions: dict[object, int] = {}
    rows = []
    for workout in week_plan.workouts:
        position = positions.get(workout.day, 0)
        positions[workout.day] = position + 1
        data = workout_to_json(workout)
        rows.append(
            PlannedWorkout(
                owner=user,
                plan=plan,
                day=workout.day,
                position=position,
                sport=workout.sport.value,
                title=workout.title,
                goal=workout.goal.value,
                duration_minutes=workout.duration_minutes,
                segments=data["segments"],
                exercises=data["exercises"],
                zone_system=workout.zone_system.value if workout.zone_system else "",
                zone=workout.zone,
                notes=workout.notes,
                slot=workout.slot.value if workout.slot else "",
                stretching_minutes=workout.stretching_minutes,
                lineage=workout.lineage or uuid.uuid7(),
            )
        )
    PlannedWorkout.objects.bulk_create(rows)
    return plan


def clean_note(note: str) -> str:
    """The note of the athlete as it is stored and told to the coach: line ends as ``\\n``,
    trimmed. Plain text with line breaks; any other control character, or more than ``NOTE_MAX``
    characters, is refused (``ValidationError`` with the field ``note``; nothing of the text is in
    the message)."""
    text = note.replace("\r\n", "\n").replace("\r", "\n").strip()
    if len(text) > NOTE_MAX:
        raise ValidationError({"note": f"Use at most {NOTE_MAX} characters."})
    if not all(char == "\n" or char.isprintable() for char in text):
        raise ValidationError({"note": "A note is plain text."})
    return text


def _clean_reason(reason: str) -> str:
    text = reason.strip()
    if len(text) > REASON_MAX:
        raise ValidationError({"reason": f"Use at most {REASON_MAX} characters."})
    if not text.isprintable():
        raise ValidationError({"reason": "A reason is one line of plain text."})
    return text
