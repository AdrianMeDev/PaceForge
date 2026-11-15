"""Sending a confirmed week to the user's Intervals.icu calendar.

One event per workout, keyed by an ``external_id`` made from the **lineage** of the workout, so
pushing the same plan again updates the events instead of adding new ones. A newer version of the
week that was made from the one before (changed by hand, restored) keeps the lineage of the
workouts it copies: its push updates their events, also where the workout was moved to another day,
and removes the events of the workouts that are gone, which ``WorkoutExport`` remembers. A version
that the coach drafted anew has new workouts and so new lineages: its push replaces the events of
the version before. PaceForge wins over Intervals.icu: an event that the user changed there is
overwritten by the next push.

Every workout is sent on its own, so each has its own result: a workout that Intervals.icu rejects
does not keep the others from arriving. A key that is refused stops the whole run (it would fail
for every workout) and a service that is busy or down stops the sending of the rest (they are
marked as failed and a later push tries again). Nothing here takes a lock while it talks to the
network: sending is idempotent, and removing an event that is gone already counts as removed.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from django.utils import timezone

from accounts.models import User
from integrations import services as integrations
from integrations.intervals import (
    IntervalsClient,
    IntervalsUnavailableError,
    RejectedError,
    UnexpectedResponseError,
)

from . import services
from .export import to_event
from .models import PlannedWorkout, WeeklyPlan, WorkoutExport
from .targets import Targets

# What is kept of a failure: a fixed code and nothing that Intervals.icu said.
REJECTED = "rejected"  # Intervals.icu does not accept the workout
UNAVAILABLE = "unavailable"  # Intervals.icu could not be reached, or is busy
UNEXPECTED = "unexpected"  # an answer that is not what the API documents

PREFIX = "paceforge-"


class NotConfirmed(Exception):
    """Only a confirmed plan is sent."""


@dataclass(frozen=True)
class PushResult:
    synced: int
    failed: int
    # Events of workouts that are gone, removed from the calendar.
    removed: int
    # Events of workouts that are gone and could not be removed this time.
    left_behind: int


@dataclass(frozen=True)
class WorkoutState:
    """Where one workout stands with Intervals.icu: ``not_sent``, ``synced`` or ``failed``."""

    status: str
    error_code: str = ""
    pushed_at: datetime | None = None


@dataclass(frozen=True)
class ExportState:
    """The workouts of a plan, in the order of the plan, and how many events of the same week are
    in the calendar for workouts that are not in this plan (an older version)."""

    workouts: tuple[WorkoutState, ...]
    older: int


NOT_SENT = "not_sent"


def external_id(lineage: UUID) -> str:
    """The key of the event of a workout at Intervals.icu. Workouts that existed before the lineage
    were their own lineage (the migration gave them their id), so their keys did not change."""
    return f"{PREFIX}{lineage}"


def export_state(user: User, plan: WeeklyPlan) -> ExportState:
    """What is known about the events of ``plan`` (two queries, however many workouts)."""
    lineages = list(
        PlannedWorkout.objects.for_user(user)
        .filter(plan=plan)
        .order_by("day", "position", "id")
        .values_list("lineage", flat=True)
    )
    rows = {
        row.external_id: row
        for row in WorkoutExport.objects.for_user(user).filter(week_start=plan.week_start)
    }
    keys = [external_id(lineage) for lineage in lineages]
    states = tuple(
        WorkoutState(row.status, row.error_code, row.pushed_at) if row else WorkoutState(NOT_SENT)
        for row in (rows.get(key) for key in keys)
    )
    return ExportState(states, older=len(rows.keys() - set(keys)))


def push(user: User, plan_id: UUID) -> PushResult:
    """Send the workouts of a confirmed plan to Intervals.icu and take away what is not in it.

    Raises ``PlanNotFound`` and ``NotConfirmed`` before anything is sent, then
    ``integrations.NotConnectedError`` and ``InvalidKeyError`` (the connection is marked invalid,
    nothing more is sent). Everything else is part of the result and of the export rows.
    """
    plan = services.get(user, plan_id)
    if plan.status != WeeklyPlan.Status.CONFIRMED:
        raise NotConfirmed
    rows = list(
        PlannedWorkout.objects.for_user(user)
        .filter(plan=plan)
        .order_by("day", "position", "id")
        .values_list("pk", "lineage")
    )
    workouts = services.load(user, plan_id).workouts  # the same order as ``rows``
    assert len(rows) == len(workouts)
    targets = Targets(user)
    wanted = {
        external_id(lineage): (pk, workout)
        for (pk, lineage), workout in zip(rows, workouts, strict=True)
    }

    def send(client: IntervalsClient) -> PushResult:
        synced = failed = 0
        down = False
        for key, (workout_id, workout) in wanted.items():
            if down:
                _fail(user, plan, workout_id, key, UNAVAILABLE)
                failed += 1
                continue
            try:
                event = client.upsert_event(to_event(workout, key, targets))
            except RejectedError:
                _fail(user, plan, workout_id, key, REJECTED)
                failed += 1
            except IntervalsUnavailableError:
                down = True
                _fail(user, plan, workout_id, key, UNAVAILABLE)
                failed += 1
            except UnexpectedResponseError:
                _fail(user, plan, workout_id, key, UNEXPECTED)
                failed += 1
            else:
                _succeed(user, plan, workout_id, key, event.id)
                synced += 1
        removed, left_behind = _remove_the_rest(user, plan, client, set(wanted), skip=down)
        return PushResult(synced, failed, removed, left_behind)

    return integrations.with_client(user, send)


def _remove_the_rest(
    user: User, plan: WeeklyPlan, client: IntervalsClient, keep: set[str], *, skip: bool
) -> tuple[int, int]:
    """Remove the events of the week that are not in ``keep``. Returns (removed, left behind)."""
    stale = list(
        WorkoutExport.objects.for_user(user)
        .filter(week_start=plan.week_start)
        .exclude(external_id__in=keep)
    )
    removed = left_behind = 0
    for export in stale:
        if skip:
            left_behind += 1
            continue
        try:
            if export.event_id is not None:
                client.delete_event(export.event_id)
        except IntervalsUnavailableError:
            skip = True  # the service is down: leave the rest for the next push
            left_behind += 1
        except UnexpectedResponseError:
            left_behind += 1
        else:
            export.delete()
            removed += 1
    return removed, left_behind


def _succeed(user: User, plan: WeeklyPlan, workout_id: UUID, key: str, event_id: int) -> None:
    WorkoutExport.objects.update_or_create(
        owner=user,
        external_id=key,
        defaults={
            "week_start": plan.week_start,
            "workout_id": workout_id,
            "status": WorkoutExport.Status.SYNCED,
            "event_id": event_id,
            "error_code": "",
            "pushed_at": timezone.now(),
        },
    )


def _fail(user: User, plan: WeeklyPlan, workout_id: UUID, key: str, code: str) -> None:
    # The event id is left as it is: a failed update leaves the earlier event in the calendar.
    WorkoutExport.objects.update_or_create(
        owner=user,
        external_id=key,
        defaults={
            "week_start": plan.week_start,
            "workout_id": workout_id,
            "status": WorkoutExport.Status.FAILED,
            "error_code": code,
            "pushed_at": timezone.now(),
        },
    )
