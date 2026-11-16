"""The skeleton of a season: the phases of the weeks up to a race, and later the volume of each.

Pure functions: no database, no Django. The numbers are product decisions, not coaching science;
each one is a constant here and is listed in ``docs/season.md`` (a test keeps the two in step).

The phases of a stretch of weeks that ends in a race are counted **back from the race**: first the
taper (the race week included), then the specific phase, the build and, if there is time, the
base. So a short preparation loses its base first and never its taper.
"""

import math
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum


class Phase(StrEnum):
    BASE = "base"
    BUILD = "build"
    SPECIFIC = "specific"
    TAPER = "taper"
    # The week after the main race, when more races follow: rest before building up again.
    TRANSITION = "transition"


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


# The phases of a stretch that ends in a race, in their order.
_STRETCH_PHASES = (Phase.BASE, Phase.BUILD, Phase.SPECIFIC, Phase.TAPER)


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
    return tuple(phase for phase in _STRETCH_PHASES for _ in range(counts[phase]))


def rolling_phases(weeks: int = ROLLING_WEEKS) -> tuple[Phase, ...]:
    """The phases of a skeleton without a race to work towards: the first half base, the rest
    build, no taper."""
    weeks = max(weeks, 0)
    base = weeks // 2
    return (Phase.BASE,) * base + (Phase.BUILD,) * (weeks - base)


# --- the volume

# How much a normal week of the base and the build adds to the week before, in percent, and after
# how many weeks of building a recovery week follows (every third week or every fourth). The
# numbers of the stories (5, 8 and 10 % a week) and of ``availability.intensity``.
RAMP_PERCENT = {"relaxed": 5, "normal": 8, "intensive": 10}
RECOVERY_EVERY = {"relaxed": 3, "normal": 4, "intensive": 4}
DEFAULT_LEVEL = "normal"
# A recovery week in percent of the week before it.
RECOVERY_PERCENT = 65
# The taper weeks in percent of the last full week, the first taper week first and the race week
# last, by the length of the taper.
TAPER_PERCENT = {1: (50,), 2: (70, 45), 3: (80, 65, 45)}
# The week of a race that comes before the main race: a mini taper, in percent of that week.
MINI_TAPER_PERCENT = 80
# The week after the main race, in percent of the last full week, and how much of it the build
# towards the next race starts with.
TRANSITION_PERCENT = 50
RESTART_PERCENT = 80
# Without a reference week: half of what the first week with time offers, but at least this much.
START_SHARE_PERCENT = 50
START_MINUTES_MIN = 60

MAIN = "main"  # the priority of an A race, as in ``goals.models.Goal.Priority``
SECONDARY = "secondary"  # B
PREPARATION = "preparation"  # C


@dataclass(frozen=True)
class Race:
    """A race of the athlete. ``priority`` is ``main`` (A), ``secondary`` (B) or ``preparation``
    (C). The title is the athlete's own text; the skeleton only carries it along."""

    day: date
    priority: str
    discipline: str | None = None
    distance_m: float | None = None
    title: str = ""


@dataclass(frozen=True)
class SkeletonInputs:
    """What the skeleton is made from.

    ``first_monday`` is the Monday of the first week. ``capacities`` is what each week offers in
    minutes (the budget applied, an absence is 0), the first week first; a week that is not in the
    list offers nothing. ``reference_minutes`` is the athlete's reference week (the higher of the
    recent average and the normal week), ``None`` if there is none.
    """

    first_monday: date
    capacities: tuple[int, ...]
    races: tuple[Race, ...] = ()
    reference_minutes: int | None = None
    level: str = DEFAULT_LEVEL


@dataclass(frozen=True)
class SkeletonWeek:
    week_start: date
    phase: Phase
    # A recovery week of the building weeks; the taper and the transition are not called that.
    recovery: bool
    target_minutes: int
    capacity_minutes: int
    # The races of this week, by date.
    races: tuple[Race, ...] = ()


@dataclass(frozen=True)
class Skeleton:
    weeks: tuple[SkeletonWeek, ...]
    # The race the phases are counted back from; ``None`` for a rolling skeleton.
    main_race: Race | None
    peak_minutes: int
    # There was no race to work towards: the weeks are base and build only.
    rolling: bool
    # The last race lies beyond ``MAX_WEEKS`` and the skeleton stops before it.
    truncated: bool


def week_index(first_monday: date, day: date) -> int:
    """The place of the week of ``day`` counted from the week of ``first_monday`` (0 for that
    week, negative before it)."""
    return (day - timedelta(days=day.weekday()) - first_monday).days // 7


def build_skeleton(inputs: SkeletonInputs) -> Skeleton:
    """The skeleton of the season: a phase, a target volume and the races of every week.

    The weeks run from ``first_monday`` to the week of the last A or B race (at most
    ``MAX_WEEKS``); without one there are ``ROLLING_WEEKS`` of base and build. The phases are
    counted back from the main race (the A race, else the latest B race). A B race before it gets a
    mini taper; after it come a transition week and a build towards each later B race. C races only
    mark their week. See ``docs/season.md`` for every number.
    """
    shaping = sorted(
        (
            race
            for race in inputs.races
            if race.priority in (MAIN, SECONDARY) and week_index(inputs.first_monday, race.day) >= 0
        ),
        key=lambda race: race.day,
    )
    main = _main_race(shaping)
    if main is None:
        phases_by_week: list[Phase] = list(rolling_phases())
        starts: set[int] = {0}
        ends: dict[int, int] = {}
        mini: set[int] = set()
        truncated = False
    else:
        phases_by_week, starts, ends, mini = _stretches(inputs.first_monday, shaping, main)
        truncated = len(phases_by_week) > MAX_WEEKS
    phases_by_week = phases_by_week[:MAX_WEEKS]
    weeks = len(phases_by_week)
    capacities = [inputs.capacities[i] if i < len(inputs.capacities) else 0 for i in range(weeks)]
    recovery = _recovery_weeks(phases_by_week, starts, inputs.level)
    targets = _targets(inputs, phases_by_week, recovery, mini, capacities, set(ends))
    races_by_week: dict[int, list[Race]] = {}
    for race in sorted(inputs.races, key=lambda race: race.day):
        races_by_week.setdefault(week_index(inputs.first_monday, race.day), []).append(race)
    result = tuple(
        SkeletonWeek(
            week_start=inputs.first_monday + timedelta(weeks=i),
            phase=phases_by_week[i],
            recovery=i in recovery,
            target_minutes=targets[i],
            capacity_minutes=capacities[i],
            races=tuple(races_by_week.get(i, ())),
        )
        for i in range(weeks)
    )
    return Skeleton(
        weeks=result,
        main_race=main,
        peak_minutes=max((week.target_minutes for week in result), default=0),
        rolling=main is None,
        truncated=truncated,
    )


def _main_race(shaping: list[Race]) -> Race | None:
    """The A race, else the latest B race; ``None`` without either."""
    for race in shaping:
        if race.priority == MAIN:
            return race
    return shaping[-1] if shaping else None


def _stretches(
    first_monday: date, shaping: list[Race], main: Race
) -> tuple[list[Phase], set[int], dict[int, int], set[int]]:
    """The phase of every week up to the last race, the weeks where a stretch begins (a stretch is
    the run of weeks that ends in a race), the weeks of the races that end one with their taper,
    and the weeks of the races that get a mini taper."""
    main_week = week_index(first_monday, main.day)
    result: list[Phase] = list(phases(main_week + 1, taper_weeks(main.discipline, main.distance_m)))
    starts = {0}
    ends = {main_week: taper_weeks(main.discipline, main.distance_m)}
    mini = {
        week_index(first_monday, race.day)
        for race in shaping
        if race.day < main.day and week_index(first_monday, race.day) < main_week
    }
    # Races after the main race that leave room for a build: a transition week comes first, then
    # every race ends a stretch of its own. A race in the transition week or in the week of the
    # one before only marks its week.
    cursor = main_week + 2
    later = [race for race in shaping if week_index(first_monday, race.day) >= cursor]
    if later:
        result.append(Phase.TRANSITION)
        starts.add(cursor)
    for race in later:
        week = week_index(first_monday, race.day)
        if week < cursor:
            continue
        taper = taper_weeks(race.discipline, race.distance_m)
        result.extend(phases(week - cursor + 1, taper))
        ends[week] = taper
        cursor = week + 1
        starts.add(cursor)
    return result, starts, ends, mini


def _recovery_weeks(phases_by_week: list[Phase], starts: set[int], level: str) -> set[int]:
    """The recovery weeks: every third or fourth building week of a stretch, but never one in the
    taper and never the week right before the taper or the end of the stretch."""
    every = RECOVERY_EVERY.get(level, RECOVERY_EVERY[DEFAULT_LEVEL])
    found: set[int] = set()
    counted = 0
    for index, phase in enumerate(phases_by_week):
        if index in starts:
            counted = 0
        if phase in (Phase.TAPER, Phase.TRANSITION):
            continue
        counted += 1
        following = phases_by_week[index + 1] if index + 1 < len(phases_by_week) else None
        before_the_end = following is None or following in (Phase.TAPER, Phase.TRANSITION)
        if counted % every == 0 and not before_the_end:
            found.add(index)
    return found


def _targets(
    inputs: SkeletonInputs,
    phases_by_week: list[Phase],
    recovery: set[int],
    mini: set[int],
    capacities: list[int],
    race_weeks: set[int],
) -> list[int]:
    """The target minutes of every week, none above what the week offers."""
    ramp = RAMP_PERCENT.get(inputs.level, RAMP_PERCENT[DEFAULT_LEVEL]) / 100
    ceiling = max(capacities, default=0)
    level = float(_start(inputs, capacities))
    ramping = False  # the first normal week is the start itself, the next ones add the ramp
    targets: list[int] = []
    for index, phase in enumerate(phases_by_week):
        cap = capacities[index]
        if phase is Phase.TAPER:
            position, run = _taper_place(phases_by_week, index, race_weeks)
            wanted = level * TAPER_PERCENT[run][position] / 100
        else:
            if phase is Phase.TRANSITION:
                wanted = level * TRANSITION_PERCENT / 100
                level *= RESTART_PERCENT / 100
                ramping = False
            elif index in recovery:
                wanted = level * RECOVERY_PERCENT / 100
            elif cap == 0:
                wanted = 0.0  # nothing to train: the level stays where it was
            else:
                if ramping and phase in (Phase.BASE, Phase.BUILD):
                    level = min(level * (1 + ramp), float(ceiling))
                level = min(level, float(ceiling)) if ceiling else level
                wanted = level
                ramping = True
        if index in mini:
            wanted *= MINI_TAPER_PERCENT / 100
        targets.append(min(_half_up(wanted), cap))
    return targets


def _taper_place(phases_by_week: list[Phase], index: int, race_weeks: set[int]) -> tuple[int, int]:
    """The place of the taper week at ``index`` in its taper (0 is the first week) and the length
    of that taper (1 to 3). A taper ends in its race week, so a taper that follows right after
    another one is a taper of its own."""
    start = index
    while start > 0 and phases_by_week[start - 1] is Phase.TAPER and start - 1 not in race_weeks:
        start -= 1
    end = index
    while end + 1 < len(phases_by_week) and end not in race_weeks:
        if phases_by_week[end + 1] is not Phase.TAPER:
            break
        end += 1
    length = min(end - start + 1, max(TAPER_PERCENT))
    return min(index - start, length - 1), length


def _start(inputs: SkeletonInputs, capacities: list[int]) -> int:
    """The volume the first normal week starts from: the reference week of the athlete, else half
    of what the first week with time offers, at least ``START_MINUTES_MIN``."""
    if inputs.reference_minutes is not None and inputs.reference_minutes > 0:
        return inputs.reference_minutes
    offered = next((minutes for minutes in capacities if minutes > 0), 0)
    return max(_half_up(offered * START_SHARE_PERCENT / 100), START_MINUTES_MIN)
