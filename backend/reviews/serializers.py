"""The shape of what the reviews API answers.

Built by hand from stored values and the results of ``reviews.matching`` and
``reviews.comparison``: nothing that identifies another user, and the user's own free text (the
note of an activity or of a week, the title and notes of a workout) only as the text it is.
"""

from datetime import date
from typing import Any

from rest_framework import serializers

from .comparison import Comparison, Figures
from .models import WeekFeedback
from .services import WeekReview

_TIME = serializers.DateTimeField()


def _time(value: Any) -> Any:
    return None if value is None else _TIME.to_representation(value)


def week_list_data(
    weeks: tuple[date, ...], workout_counts: dict[date, int], with_feedback: set[date]
) -> dict[str, Any]:
    """The weeks that can be reviewed: whether each has a confirmed plan (and how many workouts)
    and whether feedback was given."""
    return {
        "weeks": [
            {
                "week_start": week.isoformat(),
                "has_plan": week in workout_counts,
                "workout_count": workout_counts.get(week, 0),
                "has_feedback": week in with_feedback,
            }
            for week in weeks
        ]
    }


def review_data(review: WeekReview) -> dict[str, Any]:
    """One week: the plan, its workouts with the match, the activities, the comparison and the
    feedback."""
    matches = {found.workout_id: found for found in review.match.workouts}
    workout_of = {
        found.activity_id: found.workout_id
        for found in review.match.workouts
        if found.activity_id is not None
    }
    plan = review.plan
    return {
        "week_start": review.week_start.isoformat(),
        "today": review.today.isoformat(),
        "plan": (
            None
            if plan is None
            else {
                "id": str(plan.pk),
                "version": plan.version,
                "confirmed_at": _time(plan.confirmed_at),
            }
        ),
        "workouts": [
            {
                "id": str(workout.pk),
                "day": workout.day.isoformat(),
                "position": workout.position,
                "sport": workout.sport,
                "title": workout.title,
                "goal": workout.goal,
                "duration_minutes": workout.duration_minutes,
                "slot": workout.slot or None,
                "notes": workout.notes,
                "status": matches[workout.pk].status.value,
                "status_origin": matches[workout.pk].status_origin.value,
                "activity_id": _id(matches[workout.pk].activity_id),
                # "user" without an activity: the user said that none belongs to it.
                "activity_origin": _origin(matches[workout.pk].activity_origin),
            }
            for workout in review.workouts
        ],
        "activities": [
            {
                "id": str(activity.pk),
                "source": activity.source,
                "sport": activity.sport,
                "start_time": _time(activity.start_time),
                "day": review.activity_days[activity.pk].isoformat(),
                "elapsed_seconds": activity.elapsed_seconds,
                "timer_seconds": activity.timer_seconds,
                "distance_m": activity.distance_m,
                "rpe": activity.rpe,
                "notes": activity.notes,
                # The workout it belongs to; ``None``: not planned.
                "workout_id": _id(workout_of.get(activity.pk)),
            }
            for activity in review.activities
        ],
        "comparison": comparison_data(review.comparison),
        "feedback": None if review.feedback is None else feedback_data(review.feedback),
    }


def comparison_data(comparison: Comparison) -> dict[str, Any]:
    return {
        "sports": [
            {"sport": entry.sport, **_figures(entry.figures)} for entry in comparison.sports
        ],
        "total": _figures(comparison.total),
        "statuses": {status.value: count for status, count in comparison.statuses.items()},
        "done_percent": comparison.done_percent,
    }


def feedback_data(feedback: WeekFeedback) -> dict[str, Any]:
    return {
        "fatigue": feedback.fatigue,
        "motivation": feedback.motivation,
        "pain": feedback.pain,
        "notes": feedback.notes,
        "updated_at": _time(feedback.updated_at),
    }


def _figures(figures: Figures) -> dict[str, int]:
    return {
        "planned_count": figures.planned_count,
        "planned_minutes": figures.planned_minutes,
        "actual_count": figures.actual_count,
        "actual_minutes": figures.actual_minutes,
        "load": figures.load,
        "rated_count": figures.rated_count,
    }


def _id(value: Any) -> str | None:
    return None if value is None else str(value)


def _origin(value: Any) -> str | None:
    return None if value is None else str(value.value)
