"""VDOT and the threshold pace that follows from a race time. Pure functions: no database.

VDOT is the "effective VO2max" of Jack Daniels and Jimmy Gilbert: the oxygen cost of the speed a
runner held in a race, divided by the share of the maximum that a runner can sustain for that long.
It is a model of a good race, not a measurement, and it fits best for races between 5 km and the
marathon.

- oxygen cost of a speed ``v`` in metres per minute: ``-4.60 + 0.182258 v + 0.000104 v²``,
- share of the maximum that lasts ``t`` minutes: ``0.8 + 0.1894393 e^(-0.012778 t) +
  0.2989558 e^(-0.1932605 t)``.

The threshold ("T") pace is the speed whose oxygen cost is 88 % of the VDOT.
"""

import math

# The distances of the best times, in metres.
DISTANCES: dict[str, float] = {
    "5k": 5000,
    "10k": 10000,
    "half_marathon": 21097.5,
    "marathon": 42195,
}

# What a runner can be: a value outside is a typo in the time, not an athlete.
VDOT_MIN = 20.0
VDOT_MAX = 90.0

THRESHOLD_SHARE = 0.88


def _cost(metres_per_minute: float) -> float:
    return -4.60 + 0.182258 * metres_per_minute + 0.000104 * metres_per_minute**2


def _sustainable_share(minutes: float) -> float:
    return (
        0.8 + 0.1894393 * math.exp(-0.012778 * minutes) + 0.2989558 * math.exp(-0.1932605 * minutes)
    )


def vdot(distance_m: float, seconds: float) -> float | None:
    """The VDOT of a race over ``distance_m`` metres in ``seconds``; ``None`` for a distance or a
    time that is no positive finite number."""
    if not _usable(distance_m) or not _usable(seconds):
        return None
    minutes = seconds / 60
    return _cost(distance_m / minutes) / _sustainable_share(minutes)


def race_seconds(distance_m: float, value: float) -> int | None:
    """The time in whole seconds of a race over ``distance_m`` metres that is worth ``value`` VDOT
    (the inverse of ``vdot``, rounded to the second); ``None`` for a distance or a VDOT that is no
    positive finite number, or one that no time between a second and a hundred hours can reach."""
    if not _usable(distance_m) or not _usable(value):
        return None
    # ``vdot`` falls as the time grows, so the time is found by halving the interval.
    low, high = 1.0, 360_000.0
    at_low, at_high = vdot(distance_m, low), vdot(distance_m, high)
    if at_low is None or at_high is None or not at_high <= value <= at_low:
        return None
    for _ in range(80):
        middle = (low + high) / 2
        found = vdot(distance_m, middle)
        if found is None:
            return None
        if found > value:
            low = middle
        else:
            high = middle
    return round((low + high) / 2)


def threshold_pace(value: float) -> float | None:
    """The threshold pace in seconds per kilometre for a VDOT; ``None`` if it is no positive finite
    number."""
    if not _usable(value):
        return None
    # The speed at which the oxygen cost is THRESHOLD_SHARE of the VDOT: the positive root of
    # 0.000104 v² + 0.182258 v - (4.60 + cost) = 0.
    a, b, c = 0.000104, 0.182258, -(4.60 + THRESHOLD_SHARE * value)
    speed = (-b + math.sqrt(b * b - 4 * a * c)) / (2 * a)
    return 60000 / speed


def _usable(value: object) -> bool:
    return (
        isinstance(value, int | float)
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value > 0
    )
