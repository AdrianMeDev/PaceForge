"""A deterministic wellness summary: the last week against the weeks before it.

``wellness_summary`` reads all of a user's rows for the two windows in one query (so its cost does
not depend on how many rows exist) and reduces them in Python. It never touches another user's
rows. The result is pure data: the same rows and ``today`` give the same summary every time.
"""

from dataclasses import dataclass
from datetime import date, timedelta

from accounts.models import User

from .models import DailyWellness

# The two windows: the last 7 local days against the non-overlapping 28 days before them.
RECENT_DAYS = 7
BASELINE_DAYS = 28
# At least this many readings per window for a metric to be reported.
RECENT_MIN_READINGS = 3
BASELINE_MIN_READINGS = 7
# Recovery is "clearly worse than usual" when a recent mean is this far past the baseline.
# Sleep and HRV: 10% below the baseline. Resting HR: 4 bpm above the baseline.
DROPPED_PERCENT = 10
RAISED_RESTING_HR_BPM = 4

# The four metrics, in the order they are reported.
METRICS = ("sleep_minutes", "hrv", "resting_hr", "weight_kg")

# A metric whose lower values mean worse recovery (sleep, HRV) drops to warn; resting HR rises.
_DROPS = {"sleep_minutes", "hrv"}


@dataclass(frozen=True)
class MetricSummary:
    """One metric's recent mean against its baseline mean.

    ``recent`` and ``baseline`` are means over the two windows, ``None`` when there were too few
    readings. ``trend`` is ``"up"``, ``"down"`` or ``"flat"`` where both are present (``"flat"``
    only when they are exactly equal), and ``None`` otherwise.
    """

    recent: float | None
    baseline: float | None
    trend: str | None


@dataclass(frozen=True)
class WellnessSummary:
    """The four metrics, each with a 7-day mean against a 28-day baseline, plus a recovery warning.

    ``warning`` is ``True`` when any tracked recovery metric is clearly worse than usual;
    ``warning_signals`` names those metrics (``"low_sleep"``, ``"low_hrv"``, ``"high_resting_hr"``).
    """

    sleep: MetricSummary
    hrv: MetricSummary
    resting_hr: MetricSummary
    weight: MetricSummary
    warning: bool
    warning_signals: tuple[str, ...]


def wellness_summary(user: User, today: date) -> WellnessSummary:
    """The user's wellness over the last 7 days against the 28 days before, in one query."""
    baseline_start = today - timedelta(days=RECENT_DAYS + BASELINE_DAYS - 1)
    rows = list(
        DailyWellness.objects.for_user(user)
        .filter(day__gte=baseline_start, day__lte=today)
        .values_list("day", *METRICS)
    )
    recent_start = today - timedelta(days=RECENT_DAYS - 1)
    baseline_end = today - timedelta(days=RECENT_DAYS)

    summaries: dict[str, MetricSummary] = {}
    signals: list[str] = []
    for field in METRICS:
        index = METRICS.index(field) + 1  # the metrics start after ``day`` in each row
        recent = _mean(rows, recent_start, today, index, RECENT_MIN_READINGS)
        baseline = _mean(rows, baseline_start, baseline_end, index, BASELINE_MIN_READINGS)
        summary = _compare(field, recent, baseline)
        summaries[field] = summary
        if _warns(field, recent, baseline):
            signals.append(_signal_name(field))

    return WellnessSummary(
        sleep=summaries["sleep_minutes"],
        hrv=summaries["hrv"],
        resting_hr=summaries["resting_hr"],
        weight=summaries["weight_kg"],
        warning=bool(signals),
        warning_signals=tuple(signals),
    )


def wellness_data(summary: WellnessSummary | None) -> dict[str, object] | None:
    """The summary as a JSON-serializable mapping for the briefings and the dashboard.

    ``None`` in and ``None`` out: nothing stored, nothing said. The signal names are the same
    ``"low_sleep"``, ``"low_hrv"`` and ``"high_resting_hr"`` that the frontend parses.
    """
    if summary is None:
        return None
    return {
        "sleep": _metric_data(summary.sleep),
        "hrv": _metric_data(summary.hrv),
        "resting_hr": _metric_data(summary.resting_hr),
        "weight": _metric_data(summary.weight),
        "warning": summary.warning,
        "warning_signals": list(summary.warning_signals),
    }


def _mean(
    rows: list[tuple[object, ...]],
    start: date,
    end: date,
    index: int,
    minimum_readings: int,
) -> float | None:
    """The mean of the ``index``-th value over rows whose day is within ``[start, end]``.

    ``None`` when there are fewer readings than ``minimum_readings`` (a metric that is ``None`` on a
    day is not a reading).
    """
    values: list[float] = []
    for row in rows:
        day = row[0]
        value = row[index]
        if (
            isinstance(day, date)
            and start <= day <= end
            and isinstance(value, int | float)
            and not isinstance(value, bool)
        ):
            values.append(float(value))
    if len(values) < minimum_readings:
        return None
    return sum(values) / len(values)


def _compare(field: str, recent: float | None, baseline: float | None) -> MetricSummary:
    if recent is None or baseline is None:
        return MetricSummary(recent, baseline, None)
    if recent > baseline:
        trend = "up"
    elif recent < baseline:
        trend = "down"
    else:
        trend = "flat"
    return MetricSummary(recent, baseline, trend)


def _warns(field: str, recent: float | None, baseline: float | None) -> bool:
    """Whether the metric is clearly worse than usual, across both windows having enough data."""
    if recent is None or baseline is None:
        return False
    if field in _DROPS:
        return baseline - recent >= baseline * DROPPED_PERCENT / 100
    if field == "resting_hr":
        return recent >= baseline + RAISED_RESTING_HR_BPM
    # weight (and any future metric) is reported but never a recovery warning.
    return False


def _signal_name(field: str) -> str:
    if field == "sleep_minutes":
        return "low_sleep"
    if field == "hrv":
        return "low_hrv"
    if field == "resting_hr":
        return "high_resting_hr"
    return field


def _metric_data(metric: MetricSummary) -> dict[str, float | str | None]:
    return {
        "recent": _rounded(metric.recent),
        "baseline": _rounded(metric.baseline),
        "trend": metric.trend,
    }


def _rounded(value: float | None) -> float | None:
    # One decimal keeps the numbers readable and the boundaries exact where they are whole.
    return round(value, 1) if value is not None else None
