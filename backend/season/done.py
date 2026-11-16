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

from accounts.models import User
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
