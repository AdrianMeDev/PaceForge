"""How hard a plan may be: the three intensity levels and the limits of the rules they set (US-5.3).

A level is a set of starting values. The athlete may put an own value in the place of any of them;
an own value that is not set (``None``) leaves the level's value. The planning checks
(``planning.rules``) read the limits that result, the coach is told them.

The progression limits are percent of the reference week of ``planning.rules`` (the average of
the recent weeks or the typical week). The stories ask for 5, 8 and 10 % more per week; a steady
increase of that size ends at about 113, 121 and 126 % of the four weeks before, which the warning
limits round. "intensive" keeps the limits that applied to everyone before there were levels.
The running warning limit is 10 percentage points below the effective general warning limit,
but never below 100 %.

Pure data and functions: nothing here touches the database.
"""

from collections.abc import Mapping
from dataclasses import dataclass, fields, replace

from django.db import models


class IntensityLevel(models.TextChoices):
    RELAXED = "relaxed", "Relaxed"
    NORMAL = "normal", "Normal"
    INTENSIVE = "intensive", "Intensive"


@dataclass(frozen=True)
class Limits:
    # Days of the week with a hard workout, at most.
    max_hard_days: int
    # The planned minutes in percent of the reference: a warning above the first, an error above
    # the second.
    progression_warning_percent: int
    progression_error_percent: int
    # The share of easy minutes in the endurance minutes of the week, at least (a warning below).
    easy_share_percent: int

    @property
    def run_progression_warning_percent(self) -> int:
        """The stricter warning limit for running, derived from the general limit."""
        return max(
            PROGRESSION_WARNING_MIN, self.progression_warning_percent - RUN_WARNING_MARGIN_POINTS
        )


DEFAULT_LEVEL = IntensityLevel.NORMAL

LEVEL_LIMITS: dict[IntensityLevel, Limits] = {
    IntensityLevel.RELAXED: Limits(1, 115, 130, 85),
    IntensityLevel.NORMAL: Limits(2, 120, 140, 80),
    IntensityLevel.INTENSIVE: Limits(3, 130, 150, 75),
}

# The ranges an own value may take, both ends included.
HARD_DAYS_MIN = 0
HARD_DAYS_MAX = 4
PROGRESSION_WARNING_MIN = 100
PROGRESSION_WARNING_MAX = 200
RUN_WARNING_MARGIN_POINTS = 10
PROGRESSION_ERROR_MIN = 100
PROGRESSION_ERROR_MAX = 300
EASY_SHARE_MIN = 50
EASY_SHARE_MAX = 100

# The names of the limits, in the order of ``Limits``: also the names of the own values.
LIMIT_NAMES: tuple[str, ...] = tuple(field.name for field in fields(Limits))

LIMIT_RANGES: dict[str, tuple[int, int]] = {
    "max_hard_days": (HARD_DAYS_MIN, HARD_DAYS_MAX),
    "progression_warning_percent": (PROGRESSION_WARNING_MIN, PROGRESSION_WARNING_MAX),
    "progression_error_percent": (PROGRESSION_ERROR_MIN, PROGRESSION_ERROR_MAX),
    "easy_share_percent": (EASY_SHARE_MIN, EASY_SHARE_MAX),
}

# The own values: limit name to number, ``None`` for "the level's value". Missing names count as
# ``None``.
Overrides = Mapping[str, int | None]


def range_message(name: str) -> str:
    """The fixed message for an own value outside its range."""
    low, high = LIMIT_RANGES[name]
    if name == "max_hard_days":
        return f"Enter a whole number of days between {low} and {high}."
    return f"Enter a whole percent between {low} and {high}."


def effective_limits(level: str, overrides: Overrides) -> Limits:
    """The limits of ``level`` with every own value that is set in place of the level's.

    Raises ``ValueError`` for a level or a name that does not exist; the values themselves are
    taken as they are (``limit_problems`` says whether they are usable)."""
    _known(overrides)
    own = {name: value for name, value in overrides.items() if value is not None}
    return replace(LEVEL_LIMITS[IntensityLevel(level)], **own)


def limit_problems(level: str, overrides: Overrides) -> dict[str, str]:
    """What is wrong with the own values for ``level``, by name; empty if nothing is.

    Every own value must be a whole number in its range. The warning limit that results must be
    below the error limit that results, also when one of them is the level's: that problem is
    told at the own value (at the error limit if both are own)."""
    _known(overrides)
    problems: dict[str, str] = {}
    for name in LIMIT_NAMES:
        value = overrides.get(name)
        if value is None:
            continue
        low, high = LIMIT_RANGES[name]
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            problems[name] = range_message(name)
    if problems:
        return problems
    limits = effective_limits(level, overrides)
    warning, error = limits.progression_warning_percent, limits.progression_error_percent
    if warning >= error:
        at = (
            "progression_error_percent"
            if overrides.get("progression_error_percent") is not None
            else "progression_warning_percent"
        )
        problems[at] = f"The warning limit ({warning} %) must be below the error limit ({error} %)."
    return problems


def _known(overrides: Overrides) -> None:
    unknown = set(overrides) - set(LIMIT_NAMES)
    if unknown:
        raise ValueError(f"Unknown limits: {sorted(unknown)}")
