"""Is this the same session as one the user has already? One session can arrive several times: as
a file from the watch, as the same run in another format, entered by hand, synced from a platform.
The sources never agree to the second, so "the same" has a tolerance.

Two activities of one user are the same session if they have the same sport and either start at
exactly the same time (the database allows no two of those), or start within ``START_TOLERANCE`` of
each other and their durations differ by at most ``DURATION_TOLERANCE_PERCENT`` of the longer one.
A duration that one of them lacks says nothing and does not keep them apart.
"""

from datetime import datetime, timedelta

from accounts.models import User

from .models import Activity

START_TOLERANCE = timedelta(minutes=10)
DURATION_TOLERANCE_PERCENT = 10


def duration_of(timer_seconds: float | None, elapsed_seconds: float | None) -> float | None:
    """The time of a session: the timer time, the elapsed time standing in for it."""
    return timer_seconds if timer_seconds is not None else elapsed_seconds


def similar_durations(first: float | None, second: float | None) -> bool:
    if first is None or second is None:
        return True
    return abs(first - second) * 100 <= DURATION_TOLERANCE_PERCENT * max(first, second)


def find_duplicate(
    user: User, sport: str, start: datetime, seconds: float | None
) -> Activity | None:
    """The user's activity that is the same session as the one described, if there is one (with one
    query). Where several match, the one that starts closest wins."""
    nearby = Activity.objects.for_user(user).filter(
        sport=sport,
        start_time__gte=start - START_TOLERANCE,
        start_time__lte=start + START_TOLERANCE,
    )
    matches = [
        candidate
        for candidate in nearby
        if candidate.start_time == start
        or similar_durations(
            seconds, duration_of(candidate.timer_seconds, candidate.elapsed_seconds)
        )
    ]
    return min(matches, key=lambda found: abs(found.start_time - start), default=None)
