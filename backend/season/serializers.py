"""The shape of what the season API answers: built by hand from the skeleton, nothing else."""

from datetime import date
from typing import Any

from .skeleton import Phase, Race, Skeleton, SkeletonWeek


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


def skeleton_from_data(data: object) -> Skeleton:
    """The skeleton from what ``skeleton_data`` made of it, as it was stored with a plan. What is
    stored is our own, but it is read back strictly all the same: anything that is not the shape
    raises ``ValueError``."""
    item = _object(data)
    main = item["main_race"]
    weeks = item["weeks"]
    if not isinstance(weeks, list) or not isinstance(item["rolling"], bool):
        raise ValueError("The skeleton has no weeks.")
    return Skeleton(
        weeks=tuple(_week_from(week) for week in weeks),
        main_race=None if main is None else _race_from(main),
        peak_minutes=_whole(item["peak_minutes"]),
        rolling=item["rolling"],
        truncated=_boolean(item["truncated"]),
    )


def _week_from(data: object) -> SkeletonWeek:
    item = _object(data)
    races = item["races"]
    if not isinstance(races, list):
        raise ValueError("The races are not a list.")
    return SkeletonWeek(
        week_start=_date(item["week_start"]),
        phase=Phase(item["phase"]),
        recovery=_boolean(item["recovery"]),
        target_minutes=_whole(item["target_minutes"]),
        capacity_minutes=_whole(item["capacity_minutes"]),
        races=tuple(_race_from(race) for race in races),
    )


def _race_from(data: object) -> Race:
    item = _object(data)
    discipline, distance, title = item["discipline"], item["distance_m"], item["title"]
    if discipline is not None and not isinstance(discipline, str):
        raise ValueError("The discipline is not text.")
    if distance is not None and (
        isinstance(distance, bool) or not isinstance(distance, int | float)
    ):
        raise ValueError("The distance is not a number.")
    if not isinstance(title, str) or not isinstance(item["priority"], str):
        raise ValueError("The race has no title.")
    return Race(_date(item["date"]), item["priority"], discipline, distance, title)


def _object(data: object) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("Not an object.")
    return data


def _date(value: object) -> date:
    if not isinstance(value, str):
        raise ValueError("Not a date.")
    return date.fromisoformat(value)


def _whole(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("Not a count.")
    return value


def _boolean(value: object) -> bool:
    if not isinstance(value, bool):
        raise ValueError("Not a flag.")
    return value
