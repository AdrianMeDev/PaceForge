"""The load of a session, estimated from how long it was and how hard it felt.

Session RPE (Foster): minutes times the rating of perceived exertion, 1 to 10. The unit is an
arbitrary unit (AU) and **not** the training stress score (TSS) of a power meter or a platform:
the two are on different scales and must not be added up. An activity without an RPE has no load
here, and one without a duration neither: nothing is guessed.
"""

import math

from .duplicates import duration_of
from .models import Activity


def session_load(seconds: float | None, rpe: int | None) -> int | None:
    """Whole AU, rounded half up; ``None`` if the duration or the RPE is not known."""
    if seconds is None or rpe is None:
        return None
    return math.floor(seconds / 60 * rpe + 0.5)


def load_of(activity: Activity) -> int | None:
    return session_load(duration_of(activity.timer_seconds, activity.elapsed_seconds), activity.rpe)
