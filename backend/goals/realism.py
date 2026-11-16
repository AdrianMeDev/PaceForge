"""Whether the target of a goal is realistic (US-4.2). Pure functions: no database, no Django.

A running race with a distance and a target time is judged through VDOT: the form of the athlete
(the VDOT of their best time that counts) can grow by ``VDOT_GAIN_PER_WEEK`` for every week until
the race, at most ``VDOT_GAIN_MAX``. A target that asks for no more than that is **realistic**, one
that asks for up to ``AMBITIOUS_EXTRA_VDOT`` more is **ambitious**, anything more is
**unrealistic**. A threshold goal (FTP or threshold pace) is judged the same way against the
current value, with a gain in percent. The suggested target is what the form can reach by then. A
running race also gets a warning when fewer than ``PREP_WEEKS`` weeks are left for its distance.

The numbers are product decisions, not coaching science. They are in one place so that they can be
read and changed there; ``docs/goals.md`` lists them and a test keeps the page and the code in
step. The result is a hint: nothing is stored and the target of the athlete is never changed.
"""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from athletes.vdot import race_seconds, vdot

# Running: the form grows by this much VDOT for every week until the race, up to the maximum.
VDOT_GAIN_PER_WEEK = 0.2
VDOT_GAIN_MAX = 5.0
# A target up to this much VDOT above what can be reached is ambitious, above that unrealistic.
AMBITIOUS_EXTRA_VDOT = 2.0
# Thresholds: the gain in percent for every week until the date, up to the maximum, and the
# percentage points above that which are still ambitious.
THRESHOLD_GAIN_PERCENT_PER_WEEK = 0.5
THRESHOLD_GAIN_MAX_PERCENT = 15.0
AMBITIOUS_EXTRA_PERCENT = 5.0
# The distances VDOT describes well, in metres; a race outside is not judged.
MODEL_MIN_M = 1500.0
MODEL_MAX_M = 42195.0
# The weeks of preparation a running race of at most this distance (metres) should have.
PREP_WEEKS: tuple[tuple[float, int], ...] = (
    (5000.0, 4),
    (10000.0, 6),
    (21097.5, 10),
    (MODEL_MAX_M, 16),
)
# Two numbers closer than this are equal: the athlete gets the benefit of a rounding error.
_EPSILON = 1e-9


class Rating(StrEnum):
    REALISTIC = "realistic"
    AMBITIOUS = "ambitious"
    UNREALISTIC = "unrealistic"
    UNKNOWN = "unknown"


class Reason(StrEnum):
    """Why a goal could not be judged."""

    NO_MODEL = "no_model"  # another discipline, or a goal that has no target to judge
    NO_TARGET = "no_target"  # no distance or no target time (or no target value)
    OUT_OF_RANGE = "out_of_range"  # a distance VDOT does not describe
    NO_DATE = "no_date"  # no date, or a date that has passed
    NO_FORM = "no_form"  # no best time that counts, or no value to start from


@dataclass(frozen=True)
class GoalFacts:
    """What of a goal the judgement needs."""

    kind: str
    discipline: str = ""
    distance_m: float | None = None
    target_time_seconds: int | None = None
    metric: str = ""
    target_value: float | None = None
    target_date: date | None = None


@dataclass(frozen=True)
class Form:
    """What the athlete can do now, ``None`` where they have nothing: the VDOT of the best time
    that counts, the FTP in watts and the threshold pace in seconds per kilometre."""

    vdot: float | None = None
    ftp: float | None = None
    threshold_pace: float | None = None


@dataclass(frozen=True)
class Assessment:
    """The judgement of one goal.

    ``current`` and ``needed`` are in the unit of the goal's own measure (VDOT for a race, watts for
    FTP, seconds per kilometre for the threshold pace); ``suggested`` is the target that the form
    can reach by the date (seconds for a race, the unit of the measure for a threshold), the
    athlete's own target if that is realistic already. ``weeks`` are the whole weeks from today to
    the date and ``prep_weeks`` the weeks a race of this distance should have; ``prep_short`` says
    that fewer are left.
    """

    rating: Rating
    reason: Reason | None = None
    current: float | None = None
    needed: float | None = None
    suggested: float | None = None
    weeks: int | None = None
    prep_short: bool = False
    prep_weeks: int | None = None


def assess(goal: GoalFacts, form: Form, today: date) -> Assessment:
    """The judgement of ``goal`` for an athlete with ``form`` on the day ``today``."""
    if goal.kind == "race" and goal.discipline == "running":
        return _race(goal, form, today)
    if goal.kind == "threshold" and goal.metric in ("ftp", "threshold_pace"):
        return _threshold(goal, form, today)
    return Assessment(Rating.UNKNOWN, Reason.NO_MODEL)


def preparation_weeks(distance_m: float) -> int | None:
    """The weeks a running race over ``distance_m`` metres should have, ``None`` for a distance
    that is not judged."""
    if not MODEL_MIN_M <= distance_m <= MODEL_MAX_M:
        return None
    return next(weeks for limit, weeks in PREP_WEEKS if distance_m <= limit)


def weeks_until(day: date | None, today: date) -> int | None:
    """The whole weeks from ``today`` to ``day``; ``None`` without a day or for one that has
    passed (the day itself is week 0)."""
    if day is None or day < today:
        return None
    return (day - today).days // 7


def _race(goal: GoalFacts, form: Form, today: date) -> Assessment:
    distance, target = goal.distance_m, goal.target_time_seconds
    if distance is None:
        return Assessment(Rating.UNKNOWN, Reason.NO_TARGET)
    prep = preparation_weeks(distance)
    weeks = weeks_until(goal.target_date, today)
    short = prep is not None and weeks is not None and weeks < prep

    def result(rating: Rating, reason: Reason | None = None, **more: float | None) -> Assessment:
        return Assessment(rating, reason, weeks=weeks, prep_short=short, prep_weeks=prep, **more)

    if target is None:
        return result(Rating.UNKNOWN, Reason.NO_TARGET)
    if prep is None:
        return Assessment(Rating.UNKNOWN, Reason.OUT_OF_RANGE)
    if weeks is None:
        return result(Rating.UNKNOWN, Reason.NO_DATE)
    needed = vdot(distance, target)
    if needed is None:
        return result(Rating.UNKNOWN, Reason.NO_TARGET)
    if form.vdot is None:
        return result(Rating.UNKNOWN, Reason.NO_FORM, needed=_one(needed))
    reachable = form.vdot + min(VDOT_GAIN_PER_WEEK * weeks, VDOT_GAIN_MAX)
    rating = _rate(needed - reachable, AMBITIOUS_EXTRA_VDOT)
    suggested = float(target) if rating is Rating.REALISTIC else race_seconds(distance, reachable)
    return result(
        rating,
        current=_one(form.vdot),
        needed=_one(needed),
        suggested=None if suggested is None else float(suggested),
    )


def _threshold(goal: GoalFacts, form: Form, today: date) -> Assessment:
    target = goal.target_value
    if target is None or target <= 0:
        return Assessment(Rating.UNKNOWN, Reason.NO_TARGET)
    weeks = weeks_until(goal.target_date, today)
    if weeks is None:
        return Assessment(Rating.UNKNOWN, Reason.NO_DATE)
    pace = goal.metric == "threshold_pace"
    current = form.threshold_pace if pace else form.ftp
    if current is None or current <= 0:
        return Assessment(Rating.UNKNOWN, Reason.NO_FORM, needed=target, weeks=weeks)
    gain = min(THRESHOLD_GAIN_PERCENT_PER_WEEK * weeks, THRESHOLD_GAIN_MAX_PERCENT)
    if pace:
        # a faster pace is a smaller number: the gain is on the speed, which is its inverse
        asked = (current / target - 1) * 100
        reachable = current / (1 + gain / 100)
    else:
        asked = (target / current - 1) * 100
        reachable = current * (1 + gain / 100)
    rating = _rate(asked - gain, AMBITIOUS_EXTRA_PERCENT)
    suggested = target if rating is Rating.REALISTIC else float(round(reachable))
    return Assessment(rating, current=current, needed=target, suggested=suggested, weeks=weeks)


def _rate(excess: float, ambitious_extra: float) -> Rating:
    """How far above what can be reached the target lies."""
    if excess <= _EPSILON:
        return Rating.REALISTIC
    if excess <= ambitious_extra + _EPSILON:
        return Rating.AMBITIOUS
    return Rating.UNREALISTIC


def _one(value: float) -> float:
    return round(value, 1)
