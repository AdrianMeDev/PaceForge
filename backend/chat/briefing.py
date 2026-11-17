"""What the coach is told when the athlete writes to it: the week that can be changed and what the
athlete has said about their time and their body, as data.

The workouts carry the id the coach has to name in an action (their lineage, which stays the same
across the versions of a week) and say whether they can still be changed. The rest is taken from
the briefing of the week plan, so the athlete's own switches count here as well: their free text
about limitations goes along only if they turned that on.
"""

from datetime import date
from typing import Any

from accounts.models import User
from planning import briefing as week_briefing
from planning.schema import WeekPlan, Workout

# What of the briefing of the week plan the chat needs.
KEPT = (
    "week_start",
    "today",
    "days",
    "weekly_budget_minutes",
    "sports",
    "min_weekly_minutes",
    "training_days",
    "fixed_sessions",
    "limits",
    "limitations",
    "limitations_not_shown",
    "limitations_text",
)


def build_briefing(user: User, plan: WeekPlan) -> dict[str, Any]:
    """The briefing for the week of ``plan``. Only the data of ``user``."""
    base = week_briefing.build_briefing(user, plan.week_start)
    today = date.fromisoformat(base["today"])
    data = {name: base[name] for name in KEPT}
    data["workouts"] = [_workout(workout, today) for workout in plan.workouts]
    return data


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
