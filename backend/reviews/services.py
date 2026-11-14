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

from django.db import IntegrityError, transaction

from accounts.models import User
from activities.duplicates import duration_of
from activities.load import load_of
from activities.models import Activity
from goals.services import time_zone_of, today_of
from planning.models import PlannedWorkout, WeeklyPlan

from .comparison import Comparison, compare
from .matching import ActivityItem, Correction, PlannedItem, Status, WeekMatch, match_week
from .models import WeekComment, WeekFeedback, WorkoutReview

# The current week and this many weeks before it can be reviewed.
REVIEW_WEEKS = 4


# The statuses that describe an activity: they cannot be set on a workout that has none.
NEEDS_AN_ACTIVITY = frozenset({"done", "partial", "replaced"})


class WeekNotReviewable(Exception):
    """The week is not one of ``reviewable_weeks``."""


class WorkoutNotFound(Exception):
    """The user has no such workout in the confirmed plan of the week."""


class ActivityNotInWeek(Exception):
    """The user has no such activity in the week (it may exist in another week or be another
    user's: which is not said)."""


class ActivityLinkedElsewhere(Exception):
    """The activity is already assigned by hand to another workout."""


class StatusNeedsAnActivity(Exception):
    """``done``, ``partial`` and ``replaced`` describe an activity, and the workout has none."""


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
    # What the coach said about the week when asked; ``None``: it was not asked.
    comment: WeekComment | None


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
    return _build(user, monday, today)


def week_summary(user: User, monday: date) -> WeekReview | None:
    """The review of any week that has begun, for what the coach is told about the week before the
    one it plans (which is not limited to ``reviewable_weeks``). ``None`` for a week that has not
    begun yet and for one with nothing in it (see ``has_anything``). Raises ``ValueError`` unless
    ``monday`` is a Monday. The number of queries does not depend on how much data there is."""
    if monday.weekday() != 0:
        raise ValueError("A week starts on a Monday.")
    today = today_of(user)
    if monday > today - timedelta(days=today.weekday()):
        return None
    review = _build(user, monday, today)
    return review if has_anything(review) else None


def has_anything(review: WeekReview) -> bool:
    """Whether there is something to look back on: a confirmed plan, an activity or feedback."""
    return review.plan is not None or bool(review.activities) or review.feedback is not None


def _build(user: User, monday: date, today: date) -> WeekReview:
    zone = time_zone_of(user)
    plan = (
        WeeklyPlan.objects.for_user(user)
        .filter(week_start=monday, status=WeeklyPlan.Status.CONFIRMED)
        .first()
    )
    workouts = _workouts(user, monday)
    activities = _activities(user, monday, zone)
    days = {activity.pk: activity.start_time.astimezone(zone).date() for activity in activities}
    planned = [_planned(workout) for workout in workouts]
    performed = [_performed(activity, days[activity.pk]) for activity in activities]
    match = match_week(planned, performed, _corrections(user, monday), today)
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
        comment=WeekComment.objects.for_user(user).filter(week_start=monday).first(),
    )


def _weeks(today: date) -> tuple[date, ...]:
    this_week = today - timedelta(days=today.weekday())
    return tuple(this_week - timedelta(weeks=n) for n in range(REVIEW_WEEKS, -1, -1))


def _workouts(user: User, monday: date) -> list[PlannedWorkout]:
    """The workouts of the confirmed plan of the week (none without one), with one query."""
    return list(
        PlannedWorkout.objects.for_user(user).filter(
            plan__week_start=monday, plan__status=WeeklyPlan.Status.CONFIRMED
        )  # ordered by the model
    )


def _activities(user: User, monday: date, zone: tzinfo) -> list[Activity]:
    since = _local_midnight(monday, zone)
    until = _local_midnight(monday + timedelta(days=7), zone)
    return list(
        Activity.objects.for_user(user)
        .filter(start_time__gte=since, start_time__lt=until)
        .defer("laps", "best_efforts")
        .order_by("start_time", "id")
    )


def _corrections(user: User, monday: date) -> list[Correction]:
    rows = WorkoutReview.objects.for_user(user).filter(
        workout__plan__week_start=monday, workout__plan__status=WeeklyPlan.Status.CONFIRMED
    )
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


def correct(
    user: User,
    monday: date,
    workout_id: UUID,
    *,
    activity_id: UUID | None = None,
    no_activity: bool = False,
    status: str = "",
) -> WeekReview:
    """Set what the user decides about one workout of the week, replacing an earlier decision, and
    return the week as it is now. ``activity_id`` links an activity of the week, ``no_activity``
    says that none belongs to it (not both), ``status`` sets how it went (``""``: worked out from
    the activity). Nothing at all sets the workout back to the automatic match.

    Raises ``WeekNotReviewable``, ``WorkoutNotFound``, ``ActivityNotInWeek``,
    ``ActivityLinkedElsewhere`` and ``StatusNeedsAnActivity`` (a status that describes an activity
    for a workout that has none, after the correction); in each case nothing is changed.
    """
    if activity_id is not None and no_activity:
        raise ValueError("A workout has an activity or none, not both.")
    current = week_review(user, monday)  # raises WeekNotReviewable
    workout = next((item for item in current.workouts if item.pk == workout_id), None)
    if workout is None:
        raise WorkoutNotFound
    if activity_id is not None and activity_id not in current.activity_days:
        raise ActivityNotInWeek
    try:
        with transaction.atomic():
            _store(user, workout, activity_id, no_activity, status)
            after = week_review(user, monday)
            matched = next(item for item in after.match.workouts if item.workout_id == workout.pk)
            if status in NEEDS_AN_ACTIVITY and matched.activity_id is None:
                raise StatusNeedsAnActivity
    except IntegrityError:
        # Another workout of the user holds the activity (the check of the database).
        raise ActivityLinkedElsewhere from None
    return after


def save_feedback(
    user: User,
    monday: date,
    *,
    fatigue: int | None = None,
    motivation: int | None = None,
    pain: int | None = None,
    notes: str = "",
) -> WeekReview:
    """Set the feedback on the week, replacing an earlier one, and return the week as it is now.
    Feedback with nothing in it is no feedback: it is removed. Raises ``WeekNotReviewable``."""
    if monday not in reviewable_weeks(user):
        raise WeekNotReviewable
    feedback = WeekFeedback.objects.for_user(user).filter(week_start=monday)
    if fatigue is None and motivation is None and pain is None and not notes:
        feedback.delete()
    else:
        WeekFeedback.objects.update_or_create(
            owner=user,
            week_start=monday,
            defaults={
                "fatigue": fatigue,
                "motivation": motivation,
                "pain": pain,
                "notes": notes,
            },
        )
    return week_review(user, monday)


def _store(
    user: User,
    workout: PlannedWorkout,
    activity_id: UUID | None,
    no_activity: bool,
    status: str,
) -> None:
    rows = WorkoutReview.objects.for_user(user).filter(workout=workout)
    if activity_id is None and not no_activity and not status:
        rows.delete()  # back to the automatic match
        return
    WorkoutReview.objects.update_or_create(
        owner=user,
        workout=workout,
        defaults={"activity_id": activity_id, "no_activity": no_activity, "status": status},
    )
