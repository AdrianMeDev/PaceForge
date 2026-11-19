"""Strong duration deviations in the latest three completed local calendar weeks."""

from datetime import date, datetime, time, timedelta

from accounts.models import User
from activities.duplicates import duration_of
from goals.services import time_zone_of, today_of
from reviews.services import week_summary

from .models import SeasonPlanVersion
from .storage import skeleton_from_data

WEEK_COUNT = 3
LOWER_PERCENT = 70
UPPER_PERCENT = 130


def deviation_weeks(user: User, plan: SeasonPlanVersion) -> tuple[date, ...]:
    """Return evidence Mondays, oldest first, only when all three weeks qualify.

    Never search older weeks for a streak. Each week must belong to this confirmed season
    and start at or after confirmation. Unknown activity durations break the sequence;
    a confirmed week with no activities has zero actual minutes.
    """
    if (
        plan.owner_id != user.pk
        or plan.status != SeasonPlanVersion.Status.CONFIRMED
        or plan.confirmed_at is None
    ):
        return ()
    today = today_of(user)
    current = today - timedelta(days=today.weekday())
    weeks = tuple(current - timedelta(weeks=n) for n in range(WEEK_COUNT, 0, -1))
    season_weeks = {week.week_start for week in skeleton_from_data(plan.skeleton).weeks}
    zone = time_zone_of(user)
    if any(
        monday not in season_weeks
        or datetime.combine(monday, time.min, tzinfo=zone) < plan.confirmed_at
        for monday in weeks
    ):
        return ()

    for monday in weeks:
        review = week_summary(user, monday)
        if review is None or review.plan is None:
            return ()
        planned = review.comparison.total.planned_minutes
        if planned <= 0:
            return ()
        seconds = 0.0
        for activity in review.activities:
            duration = duration_of(activity.timer_seconds, activity.elapsed_seconds)
            if duration is None:
                return ()
            seconds += duration
        # Use the review's duration semantics without rounding away a threshold crossing.
        if LOWER_PERCENT * planned * 60 <= seconds * 100 <= UPPER_PERCENT * planned * 60:
            return ()
    return weeks
