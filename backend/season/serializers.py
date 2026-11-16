"""The shape of what the season API answers: built by hand from the skeleton, nothing else."""

from typing import Any

from .skeleton import Race, Skeleton, SkeletonWeek


def skeleton_data(skeleton: Skeleton) -> dict[str, Any]:
    """The skeleton as the API tells it: the weeks, the race the phases are counted back from (the
    title is the athlete's own text), the peak and whether it is a rolling or a cut-off one."""
    return {
        "rolling": skeleton.rolling,
        "truncated": skeleton.truncated,
        "main_race": None if skeleton.main_race is None else _race(skeleton.main_race),
        "peak_minutes": skeleton.peak_minutes,
        "weeks": [_week(week) for week in skeleton.weeks],
    }


def _week(week: SkeletonWeek) -> dict[str, Any]:
    return {
        "week_start": week.week_start.isoformat(),
        "phase": week.phase.value,
        "recovery": week.recovery,
        "target_minutes": week.target_minutes,
        "capacity_minutes": week.capacity_minutes,
        "races": [_race(race) for race in week.races],
    }


def _race(race: Race) -> dict[str, Any]:
    return {
        "date": race.day.isoformat(),
        "priority": race.priority,
        "discipline": race.discipline,
        "distance_m": race.distance_m,
        "title": race.title,
    }
