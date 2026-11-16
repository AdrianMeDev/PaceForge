"""Judging the goals of a user against what they can do now (``goals.realism`` has the rules).

The form comes from the user's own best times and thresholds: the VDOT of the best time that
counts (``athletes.best_times``) and the threshold values that count (``athletes.thresholds``,
whichever source holds them). Three queries (the time zone, the best times, the thresholds) however
many goals there are, and nothing of another user.
"""

from collections.abc import Iterable
from datetime import date
from typing import Any

from accounts.models import User
from athletes import best_times, thresholds

from .models import Goal
from .realism import Assessment, Form, GoalFacts, assess
from .services import today_of

RIDE_FTP = ("ride", thresholds.Metric.FTP)


def form_of(user: User) -> Form:
    """What ``user`` can do now. Two queries."""
    found = best_times.entries(user)
    return form_from(found, thresholds.all_candidates(user, found))


def form_from(
    found: list[best_times.Entry], held: dict[tuple[str, str], list[thresholds.Value]]
) -> Form:
    """The form from the best times and the threshold candidates that the caller has read already
    (``athletes.thresholds.all_candidates``)."""
    counting = best_times.counting(found)
    ftp = held.get(RIDE_FTP)
    pace = held.get(thresholds.PACE)
    return Form(
        vdot=None if counting is None else counting.vdot,
        ftp=ftp[0].value if ftp else None,
        threshold_pace=pace[0].value if pace else None,
    )


def facts_of(goal: Goal) -> GoalFacts:
    return GoalFacts(
        kind=goal.kind,
        discipline=goal.discipline,
        distance_m=goal.distance_m,
        target_time_seconds=goal.target_time_seconds,
        metric=goal.metric,
        target_value=goal.target_value,
        target_date=goal.target_date,
    )


def assess_goals(
    user: User, goals: Iterable[Goal], today: date | None = None
) -> dict[object, Assessment]:
    """The judgement of each goal by its id, for the goals of ``user`` that are active; a goal that
    is not active is not in the answer. ``today`` is the day it is for the user, looked up if the
    caller does not have it already. A goal of another user is a programming error."""
    active = [goal for goal in goals if goal.status == Goal.Status.ACTIVE]
    if any(goal.owner_id != user.pk for goal in active):
        raise ValueError("A goal of another user cannot be judged with this user's form.")
    if not active:
        return {}
    form = form_of(user)
    day = today if today is not None else today_of(user)
    return {goal.pk: assess(facts_of(goal), form, day) for goal in active}


def assessment_data(found: Assessment) -> dict[str, Any]:
    """The judgement as it is told (to the page and to the coach): fixed words and numbers, nothing
    of the athlete's text."""
    return {
        "rating": found.rating.value,
        "reason": None if found.reason is None else found.reason.value,
        "current": found.current,
        "needed": found.needed,
        "suggested": found.suggested,
        "weeks": found.weeks,
        "prep_short": found.prep_short,
        "prep_weeks": found.prep_weeks,
    }
