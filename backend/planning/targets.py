"""The numbers behind a zone of a plan: "power zone 2" as watts, heart rate as beats per minute,
pace as seconds per kilometre.

A zone of ``athletes.zones`` can be open on one side (power zone 7 has no upper bound, running
zone 1 no upper pace). A target must be a closed range, so an open side is closed here with a fixed
percentage of the threshold. The percentages are a convention, like the zones themselves.

The thresholds are those that count for the user (see ``athletes.thresholds``). Where there is none
for a zone system, or the sport has no zones (swimming, strength), there is no target: ``None``.
"""

import math
from dataclasses import dataclass

from accounts.models import User
from athletes.thresholds import all_candidates
from athletes.zones import ZoneSet, heart_rate_zones, pace_zones, power_zones

from .schema import Sport, ZoneSystem

# Percent of the threshold that closes the open low and high side of a zone set. For pace the low
# side is the fast end (fewer seconds per kilometre), so the fastest zone closes at 85 % and the
# slowest at 150 %.
_POWER = (40, 200)
_LTHR = (65, 105)
_MAX_HR = (50, 100)
_PACE = (85, 150)

_SPORT_GROUP = {Sport.CYCLING: "ride", Sport.RUNNING: "run"}


@dataclass(frozen=True)
class Target:
    """A closed range, ``low <= high``. For pace ``low`` is the faster end."""

    low: int
    high: int
    unit: str


@dataclass(frozen=True)
class _Basis:
    zones: ZoneSet
    threshold: float
    closing: tuple[int, int]


class Targets:
    """The targets of one user, from their thresholds, which are loaded once."""

    def __init__(self, user: User) -> None:
        found = all_candidates(user)

        def number(group: str, metric: str) -> float | None:
            values = found.get((group, metric))
            return values[0].value if values else None

        self._basis: dict[tuple[Sport, ZoneSystem], _Basis] = {}
        for sport, group in _SPORT_GROUP.items():
            heart_rate = heart_rate_zones(
                lthr=number(group, "lthr"), max_hr=number(group, "max_hr")
            )
            if heart_rate is not None:
                threshold = number(group, heart_rate.basis)
                if threshold is not None:
                    closing = _LTHR if heart_rate.basis == "lthr" else _MAX_HR
                    self._basis[(sport, ZoneSystem.HEART_RATE)] = _Basis(
                        heart_rate, threshold, closing
                    )
        ftp = number("ride", "ftp")
        power = power_zones(ftp)
        if power is not None and ftp is not None:
            self._basis[(Sport.CYCLING, ZoneSystem.POWER)] = _Basis(power, ftp, _POWER)
        pace_threshold = number("run", "threshold_pace")
        pace = pace_zones(pace_threshold)
        if pace is not None and pace_threshold is not None:
            self._basis[(Sport.RUNNING, ZoneSystem.PACE)] = _Basis(pace, pace_threshold, _PACE)

    def target(self, sport: Sport, system: ZoneSystem, zone: int) -> Target | None:
        basis = self._basis.get((sport, system))
        if basis is None or not 1 <= zone <= len(basis.zones.zones):
            return None
        found = basis.zones.zones[zone - 1]
        low_percent, high_percent = basis.closing
        return Target(
            low=found.lower if found.lower is not None else _percent(basis.threshold, low_percent),
            high=(
                found.upper if found.upper is not None else _percent(basis.threshold, high_percent)
            ),
            unit=found.unit,
        )


def _percent(value: float, percent: int) -> int:
    # Half up, like the zones themselves.
    return math.floor(value * percent / 100 + 0.5)
