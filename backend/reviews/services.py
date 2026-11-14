"""Putting a week together for review: the confirmed plan, the activities of the week, what the user
decided, and the match and the comparison worked out from them.

Every function acts on the data of the user it is given and on nothing else. A week is a calendar
week (Monday to Sunday) on the clock of the user's time zone, so a session just after midnight
belongs to the day the athlete lived it. The number of queries does not depend on how much data
there is.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, tzinfo
from uuid import UUID

from accounts.models import User
from activities.duplicates import duration_of
from activities.load import load_of
from activities.models import Activity
from goals.services import time_zone_of, today_of
from planning.models import PlannedWorkout, WeeklyPlan

from .comparison import Comparison, compare
from .matching import ActivityItem, Correction, PlannedItem, Status, WeekMatch, match_week
from .models import WeekFeedback, WorkoutReview

# The current week and this many weeks before it can be reviewed.
REVIEW_WEEKS = 4


class WeekNotReviewable(Exception):
    """The week is not one of ``reviewable_weeks``."""


@dataclass(frozen=True)
class WeekReview:
    """Everything about one week. ``plan`` is the confirmed plan of the week (``None``: there is
    none, then there are no workouts and every activity is not planned). ``activity_days`` is the
    local day of each activity."""

    week_start: date
    today: date
    plan: WeeklyPlan | None
    workouts: tuple[PlannedWorkout, ...]
    activities: tuple[Activity, ...]
    activity_days: dict[UUID, date]
    match: WeekMatch
    comparison: Comparison
    feedback: WeekFeedback | None


def reviewable_weeks(user: User) -> tuple[date, ...]:
    """The Mondays of the weeks that can be reviewed, the oldest first: the current week and the
    ``REVIEW_WEEKS`` before it."""
    return _weeks(today_of(user))


def week_review(user: User, monday: date) -> WeekReview:
    """The review of the week that starts on ``monday``. Raises ``WeekNotReviewable`` unless it is
    one of ``reviewable_weeks`` (which also means that it is a Monday)."""
    today = today_of(user)
    if monday not in _weeks(today):
        raise WeekNotReviewable
    zone = time_zone_of(user)
    plan = (
        WeeklyPlan.objects.for_user(user)
        .filter(week_start=monday, status=WeeklyPlan.Status.CONFIRMED)
        .first()
    )
    workouts = _workouts(user, plan)
    activities = _activities(user, monday, zone)
    days = {activity.pk: activity.start_time.astimezone(zone).date() for activity in activities}
    planned = [_planned(workout) for workout in workouts]
    performed = [_performed(activity, days[activity.pk]) for activity in activities]
    match = match_week(planned, performed, _corrections(user, plan), today)
    return WeekReview(
        week_start=monday,
        today=today,
        plan=plan,
        workouts=tuple(workouts),
        activities=tuple(activities),
        activity_days=days,
        match=match,
        comparison=compare(planned, performed, match),
        feedback=WeekFeedback.objects.for_user(user).filter(week_start=monday).first(),
    )


def _weeks(today: date) -> tuple[date, ...]:
    this_week = today - timedelta(days=today.weekday())
    return tuple(this_week - timedelta(weeks=n) for n in range(REVIEW_WEEKS, -1, -1))


def _workouts(user: User, plan: WeeklyPlan | None) -> list[PlannedWorkout]:
    if plan is None:
        return []
    return list(PlannedWorkout.objects.for_user(user).filter(plan=plan))  # ordered by the model


def _activities(user: User, monday: date, zone: tzinfo) -> list[Activity]:
    since = _local_midnight(monday, zone)
    until = _local_midnight(monday + timedelta(days=7), zone)
    return list(
        Activity.objects.for_user(user)
        .filter(start_time__gte=since, start_time__lt=until)
        .defer("laps", "best_efforts")
        .order_by("start_time", "id")
    )


def _corrections(user: User, plan: WeeklyPlan | None) -> list[Correction]:
    if plan is None:
        return []
    rows = WorkoutReview.objects.for_user(user).filter(workout__plan=plan)
    return [
        Correction(
            workout_id=row.workout_id,
            activity_id=row.activity_id,
            no_activity=row.no_activity,
            status=Status(row.status) if row.status else None,
        )
        for row in rows
    ]


def _planned(workout: PlannedWorkout) -> PlannedItem:
    return PlannedItem(
        id=workout.pk,
        day=workout.day,
        position=workout.position,
        sport=workout.sport,
        minutes=workout.duration_minutes,
    )


def _performed(activity: Activity, day: date) -> ActivityItem:
    seconds = duration_of(activity.timer_seconds, activity.elapsed_seconds)
    return ActivityItem(
        id=activity.pk,
        day=day,
        start=activity.start_time,
        sport=activity.sport,
        minutes=None if seconds is None else seconds / 60,
        rpe=activity.rpe,
        load=load_of(activity),
    )


def _local_midnight(day: date, zone: tzinfo) -> datetime:
    return datetime.combine(day, time.min, tzinfo=zone).astimezone(UTC)
