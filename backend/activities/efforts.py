"""The best efforts inside one activity: best average power and speed over fixed windows.

Pure functions on samples, no file format and no database. The samples are laid out second by
second: a value holds until the next sample, but never across a pause longer than ``MAX_GAP``
seconds, and nothing is interpolated. A sample without power or heart rate (or with an
implausible one) is treated the same way: the last value bridges it for up to ``MAX_GAP`` seconds.
The distance is never bridged: a speed window only needs a measured distance at its start and at
its end. A power window counts only if every second of it has a value, so a coffee stop never
becomes part of "the best 20 minutes".
"""

import math
from collections.abc import Iterable
from dataclasses import dataclass, field
from itertools import accumulate

POWER_WINDOWS = (5, 60, 300, 1200, 3600)
SPEED_WINDOWS = (300, 1200, 1800, 3600)
# A longer pause between two samples ends a stretch of data.
MAX_GAP = 10

MAX_POWER_W = 5000
MIN_HEART_RATE, MAX_HEART_RATE = 30, 250


@dataclass(frozen=True)
class Sample:
    seconds: float
    power: float | None = None
    distance: float | None = None  # metres from the start, growing
    heart_rate: float | None = None


@dataclass(frozen=True)
class Effort:
    """Average power (W) or speed (m/s) over the window, and the average heart rate during it
    (``None`` if there was none)."""

    value: float
    heart_rate: float | None


@dataclass(frozen=True)
class BestEfforts:
    power: dict[int, Effort] = field(default_factory=dict)
    speed: dict[int, Effort] = field(default_factory=dict)


def best_efforts(samples: Iterable[Sample]) -> BestEfforts:
    power: dict[int, Effort] = {}
    speed: dict[int, Effort] = {}
    for stretch in _stretches(_cleaned(samples)):
        watts = [second[0] for second in stretch]
        metres = [second[1] for second in stretch]
        beats = [second[2] for second in stretch]
        for window in POWER_WINDOWS:
            _keep_best(power, window, _best_average(watts, beats, window))
        for window in SPEED_WINDOWS:
            _keep_best(speed, window, _best_speed(metres, beats, window))
    return BestEfforts(power=power, speed=speed)


Second = tuple[float | None, float | None, float | None]


def _cleaned(samples: Iterable[Sample]) -> list[Sample]:
    """Sorted by time, one sample per second, implausible values dropped."""
    by_second: dict[int, Sample] = {}
    for sample in samples:
        if not _finite(sample.seconds):
            continue
        second = math.floor(sample.seconds)
        by_second.setdefault(
            second,
            Sample(
                seconds=second,
                power=_within(sample.power, 0, MAX_POWER_W),
                distance=_within(sample.distance, 0, math.inf),
                heart_rate=_within(sample.heart_rate, MIN_HEART_RATE, MAX_HEART_RATE),
            ),
        )
    ordered = [by_second[second] for second in sorted(by_second)]
    # A distance that goes backwards is a glitch, not a run in reverse.
    furthest = -math.inf
    cleaned = []
    for sample in ordered:
        distance = sample.distance
        if distance is not None:
            if distance < furthest:
                distance = None
            else:
                furthest = distance
        cleaned.append(Sample(sample.seconds, sample.power, distance, sample.heart_rate))
    return cleaned


def _stretches(samples: list[Sample]) -> list[list[Second]]:
    """Second-by-second values, split wherever two samples are more than ``MAX_GAP`` apart."""
    if not samples:
        return []
    stretches: list[list[Second]] = []
    current: list[Second] = []
    # The last known value per field, with its time: a pause ends a stretch, so a value from
    # before it is always more than MAX_GAP seconds old and never bridges into the next one.
    last: list[tuple[float, float] | None] = [None, None, None]
    for sample, following in zip(samples, [*samples[1:], None], strict=True):
        values = _bridged(sample, last)
        if following is None or following.seconds - sample.seconds > MAX_GAP:
            current.append(values)
            stretches.append(current)
            current = []
        else:
            current.extend([values] * int(following.seconds - sample.seconds))
    return [stretch for stretch in stretches if stretch]


def _bridged(sample: Sample, last: list[tuple[float, float] | None]) -> Second:
    """The sample's values; missing power or heart rate takes the last known value of up to
    ``MAX_GAP`` seconds ago. Holding a distance would fake a standstill followed by a jump."""
    result: list[float | None] = []
    for index, value in enumerate((sample.power, sample.distance, sample.heart_rate)):
        if index == 1:
            result.append(value)
        elif value is not None:
            last[index] = (sample.seconds, value)
            result.append(value)
        else:
            known = last[index]
            bridged = known is not None and sample.seconds - known[0] <= MAX_GAP
            result.append(known[1] if bridged and known is not None else None)
    return result[0], result[1], result[2]


def _best_average(
    values: list[float | None], beats: list[float | None], window: int
) -> Effort | None:
    best: tuple[float, int] | None = None
    for start, run in _runs(values):
        sums = [0.0, *accumulate(run)]
        for offset in range(len(run) - window + 1):
            average = (sums[offset + window] - sums[offset]) / window
            if best is None or average > best[0]:
                best = (average, start + offset)
    if best is None:
        return None
    return Effort(best[0], _average(beats[best[1] : best[1] + window]))


def _best_speed(
    metres: list[float | None], beats: list[float | None], window: int
) -> Effort | None:
    best: tuple[float, int] | None = None
    for offset in range(len(metres) - window):
        start, end = metres[offset], metres[offset + window]
        if start is None or end is None:
            continue
        speed = (end - start) / window
        if best is None or speed > best[0]:
            best = (speed, offset)
    if best is None:
        return None
    return Effort(best[0], _average(beats[best[1] : best[1] + window]))


def _runs(values: list[float | None]) -> list[tuple[int, list[float]]]:
    """The stretches of consecutive known values, with the index where each starts."""
    runs: list[tuple[int, list[float]]] = []
    start, run = 0, list[float]()
    for index, value in enumerate(values):
        if value is None:
            if run:
                runs.append((start, run))
            run = []
        else:
            if not run:
                start = index
            run.append(value)
    if run:
        runs.append((start, run))
    return runs


def _average(values: list[float | None]) -> float | None:
    known = [value for value in values if value is not None]
    return sum(known) / len(known) if known else None


def _keep_best(found: dict[int, Effort], window: int, effort: Effort | None) -> None:
    if effort is not None and (window not in found or effort.value > found[window].value):
        found[window] = effort


def _finite(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value)


def _within(value: float | None, minimum: float, maximum: float) -> float | None:
    if value is None or not _finite(value):
        return None
    return float(value) if minimum <= value <= maximum else None


def as_json(found: BestEfforts) -> dict[str, dict[str, dict[str, float | None]]]:
    """The efforts as stored on an activity: windows as text keys, numbers rounded."""

    def entries(efforts: dict[int, Effort], digits: int) -> dict[str, dict[str, float | None]]:
        return {
            str(window): {
                "value": round(effort.value, digits),
                "heart_rate": None if effort.heart_rate is None else round(effort.heart_rate, 1),
            }
            for window, effort in sorted(efforts.items())
        }

    return {"power": entries(found.power, 1), "speed": entries(found.speed, 4)}
