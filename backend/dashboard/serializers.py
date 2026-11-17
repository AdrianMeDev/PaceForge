"""The dashboard as it is told to the page: numbers, fixed words, ISO dates, and the athlete's own
title of the main goal."""

from typing import Any

from goals.assessing import assessment_data

from .overview import Dashboard, MainGoal, SeasonGlance
from .summary import NextWorkout, WeekFigures, WeekGlance


def dashboard_data(found: Dashboard) -> dict[str, Any]:
    return {
        "week": _week(found.week),
        "season": _season(found.season),
        "main_goal": _main_goal(found.main_goal),
        "weeks": [
            {
                "week_start": week.week_start.isoformat(),
                "sports": [{"sport": sport, "minutes": minutes} for sport, minutes in week.sports],
            }
            for week in found.weeks
        ],
        "recent": [
            {
                "id": str(item.id),
                "day": item.day.isoformat(),
                "sport": item.sport,
                "minutes": item.minutes,
            }
            for item in found.recent
        ],
        "usage": {
            "calls": found.usage.calls,
            "input_tokens": found.usage.input_tokens,
            "output_tokens": found.usage.output_tokens,
            "days": found.usage.days,
        },
    }


def _week(week: WeekGlance) -> dict[str, Any]:
    return {
        "week_start": week.week_start.isoformat(),
        "next_workout": _next_workout(week.next_workout),
        "figures": _figures(week.figures),
        "close_week": None if week.close_week is None else week.close_week.isoformat(),
    }


def _next_workout(workout: NextWorkout | None) -> dict[str, Any] | None:
    if workout is None:
        return None
    return {
        "id": workout.id,
        "day": workout.day.isoformat(),
        "sport": workout.sport,
        "title": workout.title,
        "minutes": workout.minutes,
        "zone_system": workout.zone_system,
        "zone": workout.zone,
        "sent": workout.sent,
    }


def _figures(figures: WeekFigures) -> dict[str, Any]:
    return {
        "planned_minutes": figures.planned_minutes,
        "done_minutes": figures.done_minutes,
        "workouts_done": figures.workouts_done,
        "workouts_total": figures.workouts_total,
        "average_rpe": figures.average_rpe,
    }


def _season(season: SeasonGlance | None) -> dict[str, Any] | None:
    if season is None:
        return None
    return {
        "phase": season.phase.value,
        "recovery": season.recovery,
        "target_minutes": season.target_minutes,
    }


def _main_goal(goal: MainGoal | None) -> dict[str, Any] | None:
    if goal is None:
        return None
    return {
        "id": str(goal.id),
        "title": goal.title,
        "kind": goal.kind,
        "target_date": None if goal.target_date is None else goal.target_date.isoformat(),
        "weeks_left": goal.weeks_left,
        "assessment": assessment_data(goal.assessment),
    }
