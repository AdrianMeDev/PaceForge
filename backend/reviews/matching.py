"""Which activity belongs to which planned workout of a week, and how each workout went.

A pure function on plain values: no database, no time zone, no clock. The caller says which local
day every workout and activity lies on and what "today" is; the result is the same for any order
of the input.

The automatic match: an activity belongs to the workout of the **same day and the same sport**;
several of one sport on a day pair up in order (the workouts by their position, which follows the
time of day, the activities by their start). A workout on a past day that is left without an
activity takes one that is left over on its day, whatever its sport: the session was **replaced**.
An activity belongs to at most one workout; what is left over is *not planned*.

The status of a workout with an activity of its sport is ``done`` from ``PARTIAL_BELOW_PERCENT``
of the planned minutes and ``partial`` below it (an activity without a duration is ``done``: the
shortfall is not guessed). With an activity of another sport it is ``replaced``. Without one it is
``missed`` once its day is over and ``open`` before that.

The user can correct all of it (``Correction``): link a workout to an activity of their choice,
say that it has none, or set the status. A correction that no longer fits (the activity is gone,
another workout has it, a status that needs an activity without one) is ignored, and the automatic
result stands.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

# A session of the right sport with less than this share of the planned minutes is partial.
PARTIAL_BELOW_PERCENT = 75


class Status(StrEnum):
    DONE = "done"
    PARTIAL = "partial"
    MISSED = "missed"
    REPLACED = "replaced"
    # Computed only (the day has not passed and there is no activity yet): it cannot be chosen.
    OPEN = "open"


# What the user may set by hand.
CHOOSABLE = frozenset({Status.DONE, Status.PARTIAL, Status.MISSED, Status.REPLACED})


class Origin(StrEnum):
    AUTO = "auto"
    USER = "user"


@dataclass(frozen=True)
class PlannedItem:
    """A workout of the confirmed plan: its day, its place on the day and what was planned."""

    id: UUID
    day: date
    position: int
    sport: str
    minutes: int
    planned_load: int = 0


@dataclass(frozen=True)
class ActivityItem:
    """An activity of the week, on the local day the athlete lived it. ``minutes`` is ``None``
    where the activity has no duration. ``rpe`` and ``load`` are not used by the match; they ride
    along for the comparison of the week."""

    id: UUID
    day: date
    start: datetime
    sport: str
    minutes: float | None
    rpe: int | None = None
    load: int | None = None


@dataclass(frozen=True)
class Correction:
    """What the user decided about one workout. ``activity_id`` links it to that activity,
    ``no_activity`` says that none belongs to it, ``status`` sets how it went."""

    workout_id: UUID
    activity_id: UUID | None = None
    no_activity: bool = False
    status: Status | None = None


@dataclass(frozen=True)
class WorkoutMatch:
    """The result for one workout. ``activity_origin`` is ``USER`` with no ``activity_id`` where
    the user said that no activity belongs to it."""

    workout_id: UUID
    status: Status
    status_origin: Origin
    activity_id: UUID | None
    activity_origin: Origin | None


@dataclass(frozen=True)
class WeekMatch:
    """One entry per workout in the order of the plan, and the activities of no workout (by
    start)."""

    workouts: tuple[WorkoutMatch, ...]
    unplanned: tuple[UUID, ...]


def match_week(
    workouts: Iterable[PlannedItem],
    activities: Iterable[ActivityItem],
    corrections: Iterable[Correction],
    today: date,
) -> WeekMatch:
    ordered = sorted(workouts, key=lambda item: (item.day, item.position, item.id))
    by_id = {activity.id: activity for activity in activities}
    free = sorted(by_id.values(), key=lambda item: (item.start, item.id))
    decided = {correction.workout_id: correction for correction in corrections}

    linked: dict[UUID, ActivityItem] = {}  # workout id -> activity
    origins: dict[UUID, Origin] = {}
    without: set[UUID] = set()  # workouts that get no activity
    for workout in ordered:
        correction = decided.get(workout.id)
        if correction is None:
            continue
        if correction.no_activity or correction.status is Status.MISSED:
            without.add(workout.id)
            origins[workout.id] = Origin.USER
        elif correction.activity_id is not None:
            chosen = by_id.get(correction.activity_id)
            if chosen is not None and chosen in free:  # else: gone, or another workout has it
                free.remove(chosen)
                linked[workout.id] = chosen
                origins[workout.id] = Origin.USER

    waiting = [item for item in ordered if item.id not in linked and item.id not in without]
    for workout in waiting:
        found = next((a for a in free if a.day == workout.day and a.sport == workout.sport), None)
        if found is not None:
            free.remove(found)
            linked[workout.id] = found
            origins[workout.id] = Origin.AUTO
    for workout in waiting:
        if workout.id in linked or workout.day >= today:
            continue
        found = next((a for a in free if a.day == workout.day), None)
        if found is not None:
            free.remove(found)
            linked[workout.id] = found
            origins[workout.id] = Origin.AUTO

    results = tuple(
        _result(item, linked.get(item.id), origins.get(item.id), decided.get(item.id), today)
        for item in ordered
    )
    return WeekMatch(results, tuple(activity.id for activity in free))


def _result(
    workout: PlannedItem,
    activity: ActivityItem | None,
    origin: Origin | None,
    correction: Correction | None,
    today: date,
) -> WorkoutMatch:
    status, status_origin = _automatic_status(workout, activity, today), Origin.AUTO
    chosen = correction.status if correction else None
    # Missed needs no activity (it frees the workout of one); the other three describe one.
    if chosen in CHOOSABLE and (activity is not None or chosen is Status.MISSED):
        assert chosen is not None
        status, status_origin = chosen, Origin.USER
    return WorkoutMatch(
        workout_id=workout.id,
        status=status,
        status_origin=status_origin,
        activity_id=activity.id if activity else None,
        activity_origin=origin,
    )


def _automatic_status(workout: PlannedItem, activity: ActivityItem | None, today: date) -> Status:
    if activity is None:
        return Status.MISSED if workout.day < today else Status.OPEN
    if activity.sport != workout.sport:
        return Status.REPLACED
    if activity.minutes is None:
        return Status.DONE
    enough = activity.minutes * 100 >= PARTIAL_BELOW_PERCENT * workout.minutes
    return Status.DONE if enough else Status.PARTIAL
