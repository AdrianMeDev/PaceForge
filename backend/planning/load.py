"""Read-only workout estimates and week totals on the unified activity load scale.

Segments supply a time-weighted hourly rate, scaled to the workout's declared minutes.
An unzoned segment uses the workout's zone, then its goal. Stretching adds no load.
These estimates are for comparison only; planning checks continue to use minutes.
"""

from collections.abc import Iterable
from fractions import Fraction
from math import floor
from typing import TypedDict

from activities.duplicates import duration_of
from activities.load import RPE_LOAD_PER_HOUR, load_of
from activities.models import Activity

from .schema import Goal, Sport, WeekPlan, Workout, ZoneSystem

FIVE_ZONE_LOAD_PER_HOUR = (35, 55, 75, 100, 120)
POWER_LOAD_PER_HOUR = (30, 50, 70, 95, 115, 130, 145)
GOAL_LOAD_PER_HOUR = {
    Goal.RECOVERY: 35,
    Goal.ENDURANCE: 55,
    Goal.TEMPO: 75,
    Goal.THRESHOLD: 95,
    Goal.VO2MAX: 115,
    Goal.OTHER: 55,
}
DEFAULT_STRENGTH_RPE = 6


def _zone_rate(system: ZoneSystem | None, zone: int | None, fallback: int) -> int:
    if system is None or zone is None:
        return fallback
    rates = POWER_LOAD_PER_HOUR if system == ZoneSystem.POWER else FIVE_ZONE_LOAD_PER_HOUR
    return rates[zone - 1]


def estimate_workout_load(workout: Workout) -> int:
    """Whole non-negative load points, rounded half up once after estimating the session."""
    if workout.sport == Sport.STRENGTH:
        rpes = [exercise.rpe for exercise in workout.exercises if exercise.rpe is not None]
        rpe = Fraction(sum(rpes), len(rpes)) if rpes else Fraction(DEFAULT_STRENGTH_RPE)
        rate = rpe * RPE_LOAD_PER_HOUR
    else:
        fallback = _zone_rate(
            workout.zone_system,
            workout.zone,
            GOAL_LOAD_PER_HOUR.get(workout.goal, GOAL_LOAD_PER_HOUR[Goal.OTHER]),
        )
        seconds = sum(segment.seconds * segment.repeat for segment in workout.segments)
        rate = (
            Fraction(
                sum(
                    segment.seconds
                    * segment.repeat
                    * _zone_rate(segment.zone_system, segment.zone, fallback)
                    for segment in workout.segments
                ),
                seconds,
            )
            if seconds
            else Fraction(fallback)
        )
    return max(0, floor(workout.duration_minutes * rate / 60 + Fraction(1, 2)))


class LoadFigures(TypedDict):
    planned_minutes: int
    done_minutes: int
    planned_load: int
    done_load: int


class SportLoadFigures(LoadFigures):
    sport: str


class LoadSummary(TypedDict):
    sports: list[SportLoadFigures]
    total: LoadFigures


def week_load(plan: WeekPlan, activities: Iterable[Activity]) -> LoadSummary:
    """Totals for the supplied workouts and user-scoped activities of their local week.

    Unknown activity minutes/load contribute zero. Done seconds are summed before rounding
    minutes per sport; total minutes add those rounded sport minutes, as in the week review.
    Only sports that were planned or done are listed, including unplanned ``other`` activities.
    """
    figures: dict[str, SportLoadFigures] = {}
    seconds: dict[str, float] = {}

    def of(sport: str) -> SportLoadFigures:
        return figures.setdefault(
            sport,
            {
                "sport": sport,
                "planned_minutes": 0,
                "done_minutes": 0,
                "planned_load": 0,
                "done_load": 0,
            },
        )

    for workout in plan.workouts:
        entry = of(workout.sport)
        entry["planned_minutes"] += workout.duration_minutes
        entry["planned_load"] += estimate_workout_load(workout)
    for activity in activities:
        entry = of(activity.sport)
        entry["done_load"] += load_of(activity) or 0
        seconds[activity.sport] = seconds.get(activity.sport, 0) + (
            duration_of(activity.timer_seconds, activity.elapsed_seconds) or 0
        )
    for sport, entry in figures.items():
        entry["done_minutes"] = floor(seconds.get(sport, 0) / 60 + 0.5)
    sports = [figures[sport] for sport in Activity.Sport.values if sport in figures]
    total: LoadFigures = {
        "planned_minutes": sum(entry["planned_minutes"] for entry in sports),
        "done_minutes": sum(entry["done_minutes"] for entry in sports),
        "planned_load": sum(entry["planned_load"] for entry in sports),
        "done_load": sum(entry["done_load"] for entry in sports),
    }
    return {"sports": sports, "total": total}
