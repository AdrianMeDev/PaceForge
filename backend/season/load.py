"""Read-only planned load for season weeks, using confirmed workouts when available."""

from collections import defaultdict
from collections.abc import Iterable
from datetime import date
from typing import Any

from django.db.models import FilteredRelation, Q

from accounts.models import User
from activities.load import RPE_LOAD_PER_HOUR
from planning.load import DEFAULT_STRENGTH_RPE, GOAL_LOAD_PER_HOUR, estimate_workout_load
from planning.models import WeeklyPlan
from planning.schema import Goal, Sport, parse_week_plan

from .schema import PlanWeek, SessionKind

SESSION_GOALS = {
    SessionKind.LONG: Goal.ENDURANCE,
    SessionKind.TEMPO: Goal.TEMPO,
    SessionKind.THRESHOLD: Goal.THRESHOLD,
    SessionKind.VO2MAX: Goal.VO2MAX,
    SessionKind.RACE_PACE: Goal.THRESHOLD,
    SessionKind.RACE: Goal.THRESHOLD,
    SessionKind.STRENGTH: Goal.STRENGTH,
}


def _season_load(week: PlanWeek) -> dict[str, int]:
    """Key sessions consume sport minutes; the remainder is endurance, strength uses RPE 6.

    Invalid drafts can have excess key minutes or sessions in an absent sport. Cap each
    session to the remaining sport minutes so estimates stay within the declared budget.
    Round half up once per sport, after weighting the minutes by their hourly rates.
    """
    found = {}
    for sport, minutes in week.minutes:
        if sport == Sport.STRENGTH:
            weighted = minutes * DEFAULT_STRENGTH_RPE * RPE_LOAD_PER_HOUR
        else:
            remaining = minutes
            weighted = 0
            for session in week.key_sessions:
                if session.sport != sport:
                    continue
                used = min(remaining, session.minutes)
                weighted += used * GOAL_LOAD_PER_HOUR.get(
                    SESSION_GOALS[session.kind], GOAL_LOAD_PER_HOUR[Goal.OTHER]
                )
                remaining -= used
            weighted += remaining * GOAL_LOAD_PER_HOUR[Goal.ENDURANCE]
        found[sport.value] = (weighted + 30) // 60
    return found


def planned_week_load(user: User, weeks: Iterable[PlanWeek]) -> dict[date, dict[str, int]]:
    """Planned load by sport and Monday in one user-scoped query, regardless of week count.

    A confirmed weekly plan replaces the season estimate for that week in full, including
    an empty plan. Other weekly plan versions never contribute. Workouts pass through the
    planning parser and estimator, so zones, segments and strength use the same calculation.
    """
    wanted = {week.week_start: week for week in weeks}
    if not wanted:
        return {}
    fields = (
        "day",
        "sport",
        "title",
        "goal",
        "duration_minutes",
        "segments",
        "exercises",
        "zone_system",
        "zone",
    )
    rows = (
        WeeklyPlan.objects.for_user(user)
        .filter(week_start__in=wanted, status=WeeklyPlan.Status.CONFIRMED)
        .annotate(owned_workouts=FilteredRelation("workouts", condition=Q(workouts__owner=user)))
        .order_by()
        .values("week_start", *(f"owned_workouts__{field}" for field in fields))
    )
    confirmed: dict[date, list[dict[str, Any]]] = {}
    for row in rows:
        workouts = confirmed.setdefault(row["week_start"], [])
        if row["owned_workouts__day"] is None:
            continue
        workout = {field: row[f"owned_workouts__{field}"] for field in fields}
        workout["day"] = workout["day"].isoformat()
        workout["zone_system"] = workout["zone_system"] or None
        workouts.append(workout)
    found = {}
    for monday, week in wanted.items():
        if monday not in confirmed:
            found[monday] = _season_load(week)
            continue
        plan = parse_week_plan({"week_start": monday.isoformat(), "workouts": confirmed[monday]})
        loads: dict[str, int] = defaultdict(int)
        for item in plan.workouts:
            loads[item.sport.value] += estimate_workout_load(item)
        found[monday] = dict(loads)
    return found
