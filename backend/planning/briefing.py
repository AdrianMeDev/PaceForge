"""What the coach is told about an athlete when it drafts a week: a fixed, bounded set of facts.

``build_briefing`` turns the planning context and a few more rows into plain JSON data; the prompt
(``planning.prompt``) wraps it, nothing else is ever sent. What is in it: the week and today,
what each day offers, the zone tables of the zone systems the athlete can use, the active goals,
the minutes done in recent weeks and a summary of last week's confirmed plan.

What is not in it: names, e-mail addresses, activity names or descriptions, ids of any kind, the
thresholds of sports without zones, the provider settings. The only free text is the title and
notes of a goal, cut to ``GOAL_NOTES_MAX`` characters; the prompt says that they are data and not
instructions. Size is bounded by construction (``MAX_GOALS``, the fixed zone tables) and checked in
the tests against ``MAX_BYTES``.
"""

import json
from datetime import date, timedelta
from typing import Any

from django.db.models import F

from accounts.models import User
from athletes.thresholds import all_candidates
from athletes.zones import ZoneSet, heart_rate_zones, pace_zones, power_zones
from goals.models import Goal
from goals.services import today_of

from .context import PlanContext, build_context
from .models import PlannedWorkout, WeeklyPlan
from .schema import Sport, ZoneSystem

# At most this many active goals are told, the main goal first; the rest is only counted.
MAX_GOALS = 5
# Goal notes are cut here (the model allows more); titles are short enough already.
GOAL_NOTES_MAX = 300
# The most the JSON of a briefing may take, measured in UTF-8 bytes with every free-text
# character as a six-byte escape (a control character), the worst a character can cost.
MAX_BYTES = 20_000

# The sport groups of the athlete's thresholds.
_THRESHOLD_SPORT = {Sport.CYCLING: "ride", Sport.RUNNING: "run"}


def build_briefing(user: User, monday: date) -> dict[str, Any]:
    """The briefing for the week that starts on ``monday``, as JSON-compatible data.

    The same data gives the same briefing. The number of queries does not depend on how much
    data there is.
    """
    context = build_context(user, monday)  # raises ValueError unless it is a Monday
    today = today_of(user)
    held = all_candidates(user)
    goals, goals_not_shown = _goals(user, today)
    return {
        "week_start": monday.isoformat(),
        "today": today.isoformat(),
        "days": _days(context),
        "weekly_budget_minutes": context.weekly_budget,
        "weekly_minutes_available": context.weekly_minutes,
        "zone_systems": _zone_systems(context, held),
        "goals": goals,
        "goals_not_shown": goals_not_shown,
        "recent_weeks_minutes": list(context.recent_weeks),
        # The athlete's own idea of a normal week; zero says nothing, so it is not told.
        "typical_weekly_minutes": context.typical_weekly_minutes or None,
        # The sports the athlete wants (all four if none was chosen), in the order of the format,
        # and whether stretching may be added to sessions.
        "sports": [sport.value for sport in Sport if sport in context.sports],
        "stretching": context.stretching,
        "previous_week_plan": _previous_week(user, monday),
    }


def to_json(briefing: dict[str, Any]) -> str:
    """The briefing as text: sorted keys and no spaces, so the same briefing is the same text."""
    return json.dumps(briefing, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _days(context: PlanContext) -> list[dict[str, Any]]:
    return [
        {
            "date": (context.week_start + timedelta(days=offset)).isoformat(),
            "minutes": minutes,
            "absence": absence,
        }
        for offset, (minutes, absence) in enumerate(
            zip(context.minutes, context.absences, strict=True)
        )
    ]


def _zone_systems(context: PlanContext, held: dict[tuple[str, str], list[Any]]) -> list[Any]:
    result = []
    for sport, system in sorted(context.zone_systems):
        group = _THRESHOLD_SPORT[sport]
        zone_set = _zone_set(system, group, held)
        if zone_set is None:  # cannot happen for a usable system; never send half a table
            continue
        result.append(
            {
                "sport": sport.value,
                "system": system.value,
                "threshold": {
                    "metric": zone_set.basis,
                    "value": held[(group, zone_set.basis)][0].value,
                },
                "zones": [
                    {
                        "zone": zone.number,
                        "name": zone.name,
                        "lower": zone.lower,
                        "upper": zone.upper,
                        "unit": zone.unit,
                    }
                    for zone in zone_set.zones
                ],
            }
        )
    return result


def _zone_set(
    system: ZoneSystem, group: str, held: dict[tuple[str, str], list[Any]]
) -> ZoneSet | None:
    def value(metric: str) -> float | None:
        found = held.get((group, metric))
        return found[0].value if found else None

    if system is ZoneSystem.POWER:
        return power_zones(value("ftp"))
    if system is ZoneSystem.PACE:
        return pace_zones(value("threshold_pace"))
    return heart_rate_zones(value("lthr"), value("max_hr"))


def _goals(user: User, today: date) -> tuple[list[dict[str, Any]], int]:
    active = Goal.objects.for_user(user).filter(status=Goal.Status.ACTIVE)
    # "main" sorts before "secondary"; a goal without a date comes last.
    ordered = active.order_by("priority", F("target_date").asc(nulls_last=True), "created_at", "id")
    shown = [_goal(goal, today) for goal in ordered[:MAX_GOALS]]
    return shown, max(active.count() - MAX_GOALS, 0)


def _goal(goal: Goal, today: date) -> dict[str, Any]:
    return {
        "priority": goal.priority,
        "kind": goal.kind,
        "title": goal.title,
        "notes": goal.notes[:GOAL_NOTES_MAX],
        "target_date": goal.target_date.isoformat() if goal.target_date else None,
        "days_until": (goal.target_date - today).days if goal.target_date else None,
        "discipline": goal.discipline or None,
        "distance_m": goal.distance_m,
        "target_time_seconds": goal.target_time_seconds,
        "metric": goal.metric or None,
        "target_value": goal.target_value,
    }


def _previous_week(user: User, monday: date) -> list[dict[str, Any]]:
    """The confirmed plan of the week before, one entry per workout: no titles, no notes."""
    previous = monday - timedelta(days=7)
    rows = (
        PlannedWorkout.objects.for_user(user)
        .filter(plan__week_start=previous, plan__status=WeeklyPlan.Status.CONFIRMED)
        .order_by("day", "position", "id")
        .values_list("day", "sport", "goal", "duration_minutes")
    )
    return [
        {"day": (day - previous).days, "sport": sport, "goal": goal, "minutes": minutes}
        for day, sport, goal, minutes in rows
    ]
