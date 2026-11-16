"""The skeleton of a season: the phases of the weeks up to a race, and later the volume of each.

Pure functions: no database, no Django. The numbers are product decisions, not coaching science;
each one is a constant here and is listed in ``docs/season.md`` (a test keeps the two in step).

The phases of a stretch of weeks that ends in a race are counted **back from the race**: first the
taper (the race week included), then the specific phase, the build and, if there is time, the
base. So a short preparation loses its base first and never its taper.
"""

import math
from enum import StrEnum


class Phase(StrEnum):
    BASE = "base"
    BUILD = "build"
    SPECIFIC = "specific"
    TAPER = "taper"


# The longest skeleton: a year of weeks (and the week it starts in).
MAX_WEEKS = 52
# Without a race to work towards the skeleton is this long, and has no taper.
ROLLING_WEEKS = 12

# The share of the weeks before the taper that the specific phase and the build get, and how many
# weeks the specific phase has at least and at most. The base gets the rest.
SPECIFIC_SHARE = 0.25
BUILD_SHARE = 0.35
SPECIFIC_MIN_WEEKS = 2
SPECIFIC_MAX_WEEKS = 6
# Below this many weeks before the taper there is no base; below the second number there is only
# the specific phase.
MIN_WEEKS_FOR_BASE = 6
MIN_WEEKS_FOR_BUILD = 3

# The taper in weeks (the race week included) by the distance of the race: the first number is for
# distances up to the first limit, the second up to the second limit, the third above it.
# Metres. Distances are those of the usual races with a little room.
_TAPER_LIMITS_M: dict[str, tuple[float, float]] = {
    "running": (10_000, 21_100),  # 10 km, half marathon
    "cycling": (100_000, 200_000),
    "triathlon": (51_500, 113_000),  # Olympic, 70.3
}
TAPER_WEEKS = (1, 2, 3)


def taper_weeks(discipline: str | None, distance_m: float | None) -> int:
    """How many weeks the taper of a race lasts, the race week included.

    A longer race needs a longer taper: running up to 10 km one week, up to the half marathon two,
    longer three; cycling up to 100 and 200 km and triathlon up to the Olympic and the 70.3
    distance in the same way. Swimming, a race without a distance and a discipline that is not
    known have one week.
    """
    limits = _TAPER_LIMITS_M.get(discipline or "")
    if limits is None or distance_m is None:
        return TAPER_WEEKS[0]
    short, middle = limits
    if distance_m <= short:
        return TAPER_WEEKS[0]
    if distance_m <= middle:
        return TAPER_WEEKS[1]
    return TAPER_WEEKS[2]


def _half_up(value: float) -> int:
    return math.floor(value + 0.5)


def phase_weeks(weeks: int, taper: int) -> dict[Phase, int]:
    """How many weeks each phase has in a stretch of ``weeks`` that ends in a race.

    The taper comes first (it is cut short if the stretch is shorter), the specific phase takes a
    quarter of what is left (2 to 6 weeks), the build a third, the base the rest. Below 6 weeks
    before the taper there is no base, below 3 only the specific phase.
    """
    weeks = max(weeks, 0)
    taper = min(max(taper, 0), weeks)
    before = weeks - taper
    if before < MIN_WEEKS_FOR_BUILD:
        specific, build, base = before, 0, 0
    else:
        specific = min(
            max(_half_up(SPECIFIC_SHARE * before), SPECIFIC_MIN_WEEKS), SPECIFIC_MAX_WEEKS, before
        )
        if before < MIN_WEEKS_FOR_BASE:
            build, base = before - specific, 0
        else:
            build = min(max(_half_up(BUILD_SHARE * before), 1), before - specific)
            base = before - specific - build
    return {
        Phase.BASE: base,
        Phase.BUILD: build,
        Phase.SPECIFIC: specific,
        Phase.TAPER: taper,
    }


def phases(weeks: int, taper: int) -> tuple[Phase, ...]:
    """The phase of every week of a stretch of ``weeks`` that ends in a race, the first week
    first: the base, the build, the specific phase, the taper."""
    counts = phase_weeks(weeks, taper)
    return tuple(phase for phase in Phase for _ in range(counts[phase]))


def rolling_phases(weeks: int = ROLLING_WEEKS) -> tuple[Phase, ...]:
    """The phases of a skeleton without a race to work towards: the first half base, the rest
    build, no taper."""
    weeks = max(weeks, 0)
    base = weeks // 2
    return (Phase.BASE,) * base + (Phase.BUILD,) * (weeks - base)
