"""Training zones computed from thresholds. Pure functions: no database, no user.

The zone models are published conventions; athletes and coaches differ in the details, so the
numbers here are a starting point, not a truth:

- power, as a percentage of FTP: the seven levels of Andrew Coggan,
- heart rate, as a percentage of the lactate threshold heart rate (LTHR): five zones after Joe
  Friel; if only the maximum heart rate is known, as a percentage of that,
- running pace, as a percentage of the threshold pace: five zones after Joe Friel.

Every zone is half open: ``lower`` is included, ``upper`` is not, and ``None`` means that the zone
has no limit on that side. Values are whole watts, beats or seconds per kilometre, rounded half
up. Pace is time per distance, so zones run from slow to fast and their bounds *fall*: zone 1 has
no upper bound, and its lower bound is the upper bound of zone 2.

A missing or implausible threshold (zero, negative, not a number) gives ``None``, never an error.
"""

import math
from dataclasses import dataclass
from typing import TypeGuard

WATTS = "W"
BPM = "bpm"
SECONDS_PER_KM = "s/km"


@dataclass(frozen=True)
class Zone:
    number: int
    name: str
    lower: int | None
    upper: int | None
    unit: str


@dataclass(frozen=True)
class ZoneSet:
    """The zones together with the threshold they are based on (``ftp``, ``lthr``, ``max_hr`` or
    ``threshold_pace``)."""

    basis: str
    zones: tuple[Zone, ...]


# Percent of the threshold at which one zone ends and the next begins, and the zone names.
_POWER_BOUNDS = (55, 75, 90, 105, 120, 150)
_POWER_NAMES = (
    "Active recovery",
    "Endurance",
    "Tempo",
    "Threshold",
    "VO2max",
    "Anaerobic capacity",
    "Neuromuscular power",
)
_LTHR_BOUNDS = (85, 90, 95, 100)
_LTHR_NAMES = ("Recovery", "Aerobic", "Tempo", "Sub-threshold", "Super-threshold")
_MAX_HR_BOUNDS = (60, 70, 80, 90)
_MAX_HR_NAMES = ("Very light", "Light", "Moderate", "Hard", "Maximum")
# Pace: the percentages are of the threshold pace in seconds per km, so above 100 is slower.
_PACE_BOUNDS = (129, 114, 106, 99)
_PACE_NAMES = ("Recovery", "Aerobic", "Tempo", "Threshold", "Interval")


def power_zones(ftp: float | None) -> ZoneSet | None:
    if not _usable(ftp):
        return None
    return ZoneSet("ftp", _rising(ftp, _POWER_BOUNDS, _POWER_NAMES, WATTS))


def heart_rate_zones(lthr: float | None = None, max_hr: float | None = None) -> ZoneSet | None:
    """From the lactate threshold heart rate if there is one, otherwise from the maximum."""
    if _usable(lthr):
        return ZoneSet("lthr", _rising(lthr, _LTHR_BOUNDS, _LTHR_NAMES, BPM))
    if _usable(max_hr):
        return ZoneSet("max_hr", _rising(max_hr, _MAX_HR_BOUNDS, _MAX_HR_NAMES, BPM))
    return None


def pace_zones(threshold_pace: float | None) -> ZoneSet | None:
    if not _usable(threshold_pace):
        return None
    edges = [_percent_of(threshold_pace, percent) for percent in _PACE_BOUNDS]
    zones = tuple(
        Zone(
            number=index + 1,
            name=name,
            lower=edges[index] if index < len(edges) else None,
            upper=edges[index - 1] if index > 0 else None,
            unit=SECONDS_PER_KM,
        )
        for index, name in enumerate(_PACE_NAMES)
    )
    return ZoneSet("threshold_pace", zones)


def _rising(
    threshold: float, bounds: tuple[int, ...], names: tuple[str, ...], unit: str
) -> tuple[Zone, ...]:
    edges = [_percent_of(threshold, percent) for percent in bounds]
    return tuple(
        Zone(
            number=index + 1,
            name=name,
            lower=edges[index - 1] if index > 0 else None,
            upper=edges[index] if index < len(edges) else None,
            unit=unit,
        )
        for index, name in enumerate(names)
    )


def _percent_of(value: float, percent: int) -> int:
    return math.floor(value * percent / 100 + 0.5)


def _usable(value: object) -> TypeGuard[float]:
    return (
        isinstance(value, int | float)
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value > 0
    )
