"""What the coach is told about a finished week when it is asked to comment on it: a fixed,
bounded set of numbers and fixed words.

``build_briefing`` turns a ``WeekReview`` into plain JSON data; the prompt (``reviews.prompt``)
wraps it, nothing else is ever sent. What is in it: for each workout its day (0 for Monday), sport,
goal, planned minutes, status, the minutes of the activity that belongs to it and its RPE; the
sessions that were not planned (day, sport, minutes, RPE); planned against done per sport and in
all; the statuses; the share done; and the three scales of the week feedback.

What is not in it, whatever the user wrote: the title and notes of a workout, the note of an
activity, the note of the week, ids, names, dates other than the week and today, the coach's own
earlier comment. There is no free text in it at all, so nothing in it can ask the model to do
anything. Size is bounded by construction (``MAX_UNPLANNED``, the limits of a plan) and checked in
the tests against ``MAX_BYTES``.
"""

import json
from typing import Any

from activities.duplicates import duration_of
from activities.models import Activity

from .comparison import Figures
from .services import WeekReview

# At most this many sessions that were not planned are told, in the order they were done; the rest
# is only counted.
MAX_UNPLANNED = 20
# The most the JSON of a briefing may take, in UTF-8 bytes; checked in the tests with a week at the
# limits of a plan (which takes about 4.7 KB: there is no free text in it).
MAX_BYTES = 8_000


def build_briefing(review: WeekReview) -> dict[str, Any]:
    """The briefing for one week, as JSON-compatible data. The same week gives the same briefing."""
    activities = {activity.pk: activity for activity in review.activities}
    workouts = []
    for workout, found in zip(review.workouts, review.match.workouts, strict=True):
        assert found.workout_id == workout.pk  # both are in the order of the plan
        done = activities[found.activity_id] if found.activity_id is not None else None
        workouts.append(
            {
                "day": (workout.day - review.week_start).days,
                "sport": workout.sport,
                "goal": workout.goal,
                "planned_minutes": workout.duration_minutes,
                "status": found.status.value,
                "done_minutes": _minutes(done),
                "rpe": done.rpe if done is not None else None,
            }
        )
    not_planned = [activities[ident] for ident in review.match.unplanned]
    comparison = review.comparison
    feedback = review.feedback
    return {
        "week_start": review.week_start.isoformat(),
        "today": review.today.isoformat(),
        "workouts": workouts,
        "unplanned": [
            {
                "day": (review.activity_days[activity.pk] - review.week_start).days,
                "sport": activity.sport,
                "minutes": _minutes(activity),
                "rpe": activity.rpe,
            }
            for activity in not_planned[:MAX_UNPLANNED]
        ],
        "unplanned_not_shown": max(len(not_planned) - MAX_UNPLANNED, 0),
        "sports": [
            {"sport": entry.sport, **_figures(entry.figures)} for entry in comparison.sports
        ],
        "total": _figures(comparison.total),
        "statuses": {status.value: count for status, count in comparison.statuses.items()},
        "done_percent": comparison.done_percent,
        "feedback": (
            None
            if feedback is None
            else {
                "fatigue": feedback.fatigue,
                "motivation": feedback.motivation,
                "pain": feedback.pain,
            }
        ),
    }


def to_json(briefing: dict[str, Any]) -> str:
    """The briefing as text: sorted keys and no spaces, so the same briefing is the same text."""
    return json.dumps(briefing, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _minutes(activity: Activity | None) -> int | None:
    """Whole minutes of an activity, half up; ``None`` without an activity or a duration."""
    if activity is None:
        return None
    seconds = duration_of(activity.timer_seconds, activity.elapsed_seconds)
    return None if seconds is None else int(seconds / 60 + 0.5)


def _figures(figures: Figures) -> dict[str, int]:
    return {
        "planned_count": figures.planned_count,
        "planned_minutes": figures.planned_minutes,
        "actual_count": figures.actual_count,
        "actual_minutes": figures.actual_minutes,
        "load": figures.load,
        "rated_count": figures.rated_count,
    }
