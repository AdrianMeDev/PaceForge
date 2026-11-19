"""The minutes the athlete actually trained, per week and sport, for the chart of the season.

The weeks are calendar weeks (Monday to Sunday) in the time zone of the athlete, so that an
activity just after midnight counts for the day they lived it, as for the recent weeks of the week
plan. The timer time counts, the elapsed time stands in for it, and an activity with neither has
no duration and does not count. Two queries, whatever the number of weeks: the time zone and the
activities.
"""

from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, date, datetime, time, timedelta
from typing import TypedDict

from accounts.models import User
from activities.duplicates import duration_of
from activities.load import load_of
from activities.models import Activity
from goals.services import time_zone_of

# The sports in the order the chart stacks them; ``other`` is what no sport of the plan covers.
SPORT_ORDER = ("running", "cycling", "swimming", "strength", "other")


def done_minutes(user: User, mondays: Iterable[date]) -> dict[date, list[tuple[str, int]]]:
    """For each Monday of ``mondays`` the minutes done in that week as ``(sport, minutes)`` in the
    order of ``SPORT_ORDER``, only the sports with at least one minute. A week without any
    activity is an empty list, not missing. Minutes are the seconds of the week and sport added up
    first and then rounded to whole minutes (half up)."""
    wanted = sorted(set(mondays))
    if not wanted:
        return {}
    zone = time_zone_of(user)
    since = datetime.combine(wanted[0], time.min, tzinfo=zone).astimezone(UTC)
    until = datetime.combine(wanted[-1] + timedelta(days=7), time.min, tzinfo=zone).astimezone(UTC)
    rows = (
        Activity.objects.for_user(user)
        .filter(start_time__gte=since, start_time__lt=until)
        .values_list("start_time", "sport", "timer_seconds", "elapsed_seconds")
    )
    seconds: dict[tuple[date, str], float] = defaultdict(float)
    for start, sport, timer, elapsed in rows:
        duration = timer if timer is not None else elapsed
        if duration is None:
            continue
        day = start.astimezone(zone).date()
        seconds[(day - timedelta(days=day.weekday()), sport)] += duration
    found: dict[date, list[tuple[str, int]]] = {}
    for monday in wanted:
        entries = [(sport, int(seconds[(monday, sport)] / 60 + 0.5)) for sport in SPORT_ORDER]
        found[monday] = [(sport, minutes) for sport, minutes in entries if minutes > 0]
    return found


class WeekTotals(TypedDict):
    minutes: list[tuple[str, int]]
    load: list[tuple[str, int]]


def done_week_totals(user: User, mondays: Iterable[date]) -> dict[date, WeekTotals]:
    """Done minutes and load in two queries, with the same local weeks as ``done_minutes``.

    Minutes sum seconds before rounding. Load sums the rounded load of each activity,
    preferring Intervals load and otherwise using duration and RPE. Unknown load adds zero.
    Only positive sport totals are listed; a requested empty week has two empty lists.
    """
    wanted = sorted(set(mondays))
    if not wanted:
        return {}
    zone = time_zone_of(user)
    since = datetime.combine(wanted[0], time.min, tzinfo=zone).astimezone(UTC)
    until = datetime.combine(wanted[-1] + timedelta(days=7), time.min, tzinfo=zone).astimezone(UTC)
    activities = (
        Activity.objects.for_user(user)
        .filter(start_time__gte=since, start_time__lt=until)
        .only("start_time", "sport", "timer_seconds", "elapsed_seconds", "training_load", "rpe")
    )
    seconds: dict[tuple[date, str], float] = defaultdict(float)
    loads: dict[tuple[date, str], int] = defaultdict(int)
    for activity in activities:
        day = activity.start_time.astimezone(zone).date()
        key = (day - timedelta(days=day.weekday()), activity.sport)
        seconds[key] += duration_of(activity.timer_seconds, activity.elapsed_seconds) or 0
        loads[key] += load_of(activity) or 0
    found: dict[date, WeekTotals] = {}
    for monday in wanted:
        minutes = [(sport, int(seconds[(monday, sport)] / 60 + 0.5)) for sport in SPORT_ORDER]
        found[monday] = {
            "minutes": [(sport, amount) for sport, amount in minutes if amount > 0],
            "load": [
                (sport, loads[(monday, sport)])
                for sport in SPORT_ORDER
                if loads[(monday, sport)] > 0
            ],
        }
    return found
