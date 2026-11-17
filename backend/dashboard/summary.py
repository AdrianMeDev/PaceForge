"""What the dashboard says about the current week: the next workout, the figures of the week and
whether a week is waiting to be closed.

Everything comes from the services that already know the week (``reviews.services``); nothing is
worked out twice. Every function acts on the data of the user it is given and on nothing else.
The number of queries does not depend on how much data there is: the plan of next week and the
exports are always read, also when they turn out not to be needed.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from uuid import UUID

from accounts.models import User
from goals.services import today_of
from planning.models import PlannedWorkout, WeeklyPlan, WorkoutExport
from reviews.matching import Status
from reviews.services import WeekReview, week_review, week_summary


@dataclass(frozen=True)
class NextWorkout:
    """The workout that is next. ``sent`` says that it is at Intervals.icu."""

    id: str
    day: date
    sport: str
    title: str
    minutes: int
    zone_system: str
    zone: int | None
    sent: bool


@dataclass(frozen=True)
class WeekFigures:
    """The current week in numbers. ``average_rpe`` is the mean of the ratings of the activities
    that have one, to one decimal; ``None`` while none is rated."""

    planned_minutes: int
    done_minutes: int
    workouts_done: int
    workouts_total: int
    average_rpe: float | None


@dataclass(frozen=True)
class WeekGlance:
    """``close_week`` is the Monday of the week to close (looking back and giving feedback), or
    ``None``."""

    week_start: date
    next_workout: NextWorkout | None
    figures: WeekFigures
    close_week: date | None


def week_glance(user: User) -> WeekGlance:
    today = today_of(user)
    monday = today - timedelta(days=today.weekday())
    review = week_review(user, monday)
    after = _confirmed_workouts(user, monday + timedelta(weeks=1))
    sent = _sent(user, (monday, monday + timedelta(weeks=1)))
    return WeekGlance(
        week_start=monday,
        next_workout=_next_workout(review, after, sent, today),
        figures=_figures(review),
        close_week=_close_week(user, review, today),
    )


def _confirmed_workouts(user: User, monday: date) -> list[PlannedWorkout]:
    return list(
        PlannedWorkout.objects.for_user(user).filter(
            plan__week_start=monday, plan__status=WeeklyPlan.Status.CONFIRMED
        )
    )


def _sent(user: User, mondays: tuple[date, ...]) -> set[UUID]:
    """The ids of the workouts that are at Intervals.icu (of the weeks that start on
    ``mondays``)."""
    return set(
        WorkoutExport.objects.for_user(user)
        .filter(week_start__in=mondays, status=WorkoutExport.Status.SYNCED)
        .exclude(workout=None)
        .values_list("workout_id", flat=True)
    )


def _next_workout(
    review: WeekReview, after: list[PlannedWorkout], sent: set[UUID], today: date
) -> NextWorkout | None:
    """The first workout of this week that is today or later and still open; failing that, the
    first of the confirmed plan of next week."""
    open_ids = {found.workout_id for found in review.match.workouts if found.status is Status.OPEN}
    candidates = [w for w in review.workouts if w.pk in open_ids and w.day >= today]
    workout = candidates[0] if candidates else (after[0] if after else None)
    if workout is None:
        return None
    return NextWorkout(
        id=str(workout.pk),
        day=workout.day,
        sport=workout.sport,
        title=workout.title,
        minutes=workout.duration_minutes,
        zone_system=workout.zone_system,
        zone=workout.zone,
        sent=workout.pk in sent,
    )


def _figures(review: WeekReview) -> WeekFigures:
    total = review.comparison.total
    ratings = [activity.rpe for activity in review.activities if activity.rpe is not None]
    return WeekFigures(
        planned_minutes=total.planned_minutes,
        done_minutes=total.actual_minutes,
        workouts_done=review.comparison.statuses[Status.DONE],
        workouts_total=len(review.workouts),
        average_rpe=round(sum(ratings) / len(ratings), 1) if ratings else None,
    )


def _close_week(user: User, review: WeekReview, today: date) -> date | None:
    """This week on a Sunday, when there is something in it and no feedback yet; else last week,
    when it has something to look back on and no feedback."""
    this_week_has_work = review.plan is not None or bool(review.activities)
    if today.weekday() == 6 and this_week_has_work and review.feedback is None:
        return review.week_start
    before = week_summary(user, review.week_start - timedelta(weeks=1))
    if before is not None and before.feedback is None:
        return before.week_start
    return None
