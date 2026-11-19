"""What the coach is told when the athlete writes to it: the weeks ahead that have a plan and what
the athlete has said about their time and their body, as data.

The workouts carry the id the coach has to name in an action (their lineage, which stays the same
across the versions of a week) and say whether they can still be changed. The rest is taken from
the briefing of the week plan, so the athlete's own switches count here as well: their free text
about limitations goes along only if they turned that on.
"""

from collections.abc import Sequence
from datetime import date, timedelta
from typing import Any

from accounts.models import User
from goals.services import today_of
from planning import briefing as week_briefing
from planning.schema import WeekPlan, Workout

# What of the briefing of the week plan the chat shares across all weeks.
KEPT = (
    "today",
    "sports",
    "min_weekly_minutes",
    "training_days",
    "fixed_sessions",
    "limits",
    "limitations",
    "limitations_not_shown",
    "limitations_text",
    "wellness",
)

# What of the briefing of the week plan is kept per week.
WEEK_KEPT = (
    "week_start",
    "days",
    "weekly_budget_minutes",
)


def build_briefing(user: User, plans: Sequence[WeekPlan]) -> dict[str, Any]:
    """The briefing for ``plans``, ordered by week start. Only the data of ``user``."""
    ordered = sorted(plans, key=lambda plan: plan.week_start)
    if ordered:
        bases = [week_briefing.build_briefing(user, plan.week_start) for plan in ordered]
        first = bases[0]
    else:
        today = today_of(user)
        this_week = today - timedelta(days=today.weekday())
        bases = []
        first = week_briefing.build_briefing(user, this_week)
    today = date.fromisoformat(first["today"])
    data: dict[str, Any] = {name: first[name] for name in KEPT}
    data["weeks"] = [_week(base, plan, today) for base, plan in zip(bases, ordered, strict=True)]
    return data


def _week(base: dict[str, Any], plan: WeekPlan, today: date) -> dict[str, Any]:
    return {
        **{name: base[name] for name in WEEK_KEPT},
        "workouts": [_workout(workout, today) for workout in plan.workouts],
    }


def _workout(workout: Workout, today: date) -> dict[str, Any]:
    return {
        # Every workout of a stored plan has a lineage.
        "id": str(workout.lineage),
        "day": workout.day.isoformat(),
        "slot": workout.slot.value if workout.slot else None,
        "sport": workout.sport.value,
        "title": workout.title,
        "goal": workout.goal.value,
        "minutes": workout.duration_minutes,
        "zone_system": workout.zone_system.value if workout.zone_system else None,
        "zone": workout.zone,
        "changeable": workout.day >= today,
    }
