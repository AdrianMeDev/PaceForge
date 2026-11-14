"""Planned against actual for one week: counts, minutes and load, in all and per sport.

Pure arithmetic on the planned workouts, the activities of the week and their match
(``reviews.matching``). Planned minutes are those of the workouts; actual minutes are those of
**every** activity of the week, matched or not, so that a session nobody planned still counts as
training done. The load is the sum of the loads (minutes times RPE, in AU, which is not TSS) of
the activities that have one; ``rated_count`` says how many that is, so that a low load of a week
with few ratings is not mistaken for an easy week. There is no planned load: workouts have none yet.
"""

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from math import floor

from .matching import ActivityItem, PlannedItem, Status, WeekMatch

# The order sports are listed in: the sports of a plan first, then what a plan has no word for.
SPORT_ORDER = ("running", "cycling", "swimming", "strength", "other")


@dataclass(frozen=True)
class Figures:
    planned_count: int
    planned_minutes: int
    actual_count: int
    actual_minutes: int
    load: int
    rated_count: int


@dataclass(frozen=True)
class SportFigures:
    sport: str
    figures: Figures


@dataclass(frozen=True)
class Comparison:
    """``sports`` holds the sports that were planned or done, in ``SPORT_ORDER``; ``total`` is
    their sum. ``statuses`` counts the workouts by status (every status is present, also at 0).
    ``done_percent`` is the share of the workouts that are done among those that are not open,
    rounded half up; ``None`` while none of them is."""

    sports: tuple[SportFigures, ...]
    total: Figures
    statuses: dict[Status, int]
    done_percent: int | None


def compare(
    workouts: Iterable[PlannedItem], activities: Iterable[ActivityItem], match: WeekMatch
) -> Comparison:
    planned = list(workouts)
    done = list(activities)
    known = [sport for sport in SPORT_ORDER if _involved(sport, planned, done)]
    # A sport that is not in the order (cannot happen with the stored choices) is listed last.
    named = {item.sport for item in planned} | {item.sport for item in done}
    extra = sorted(named - set(SPORT_ORDER))
    sports = tuple(
        SportFigures(sport, _figures([w for w in planned if w.sport == sport], _of(done, sport)))
        for sport in (*known, *extra)
    )
    total = Figures(
        planned_count=sum(entry.figures.planned_count for entry in sports),
        planned_minutes=sum(entry.figures.planned_minutes for entry in sports),
        actual_count=sum(entry.figures.actual_count for entry in sports),
        actual_minutes=sum(entry.figures.actual_minutes for entry in sports),
        load=sum(entry.figures.load for entry in sports),
        rated_count=sum(entry.figures.rated_count for entry in sports),
    )
    counted = Counter(result.status for result in match.workouts)
    statuses = {status: counted[status] for status in Status}
    judged = len(match.workouts) - statuses[Status.OPEN]
    percent = None if judged == 0 else (200 * statuses[Status.DONE] + judged) // (2 * judged)
    return Comparison(sports, total, statuses, percent)


def _involved(sport: str, planned: list[PlannedItem], done: list[ActivityItem]) -> bool:
    return any(item.sport == sport for item in planned) or bool(_of(done, sport))


def _of(done: list[ActivityItem], sport: str) -> list[ActivityItem]:
    return [item for item in done if item.sport == sport]


def _figures(planned: list[PlannedItem], done: list[ActivityItem]) -> Figures:
    minutes = sum(item.minutes or 0 for item in done)
    return Figures(
        planned_count=len(planned),
        planned_minutes=sum(item.minutes for item in planned),
        actual_count=len(done),
        # Whole minutes, half up; the total adds up the rounded minutes of the sports.
        actual_minutes=floor(minutes + 0.5),
        load=sum(item.load or 0 for item in done),
        rated_count=sum(1 for item in done if item.rpe is not None),
    )
