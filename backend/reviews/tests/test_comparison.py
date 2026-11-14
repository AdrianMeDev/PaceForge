from datetime import UTC, date, datetime, timedelta
from uuid import UUID

import pytest

from reviews.comparison import SPORT_ORDER, Comparison, Figures, compare
from reviews.matching import ActivityItem, Correction, PlannedItem, Status, match_week

MONDAY = date(2026, 11, 9)
LATER = MONDAY + timedelta(days=14)  # every day of the week is over


def uid(number: int) -> UUID:
    return UUID(int=number)


def planned(
    number: int, day: int = 0, sport: str = "running", minutes: int = 60, position: int = 0
) -> PlannedItem:
    return PlannedItem(uid(number), MONDAY + timedelta(days=day), position, sport, minutes)


def performed(
    number: int,
    day: int = 0,
    sport: str = "running",
    minutes: float | None = 60,
    rpe: int | None = None,
    load: int | None = None,
) -> ActivityItem:
    when = MONDAY + timedelta(days=day)
    start = datetime(when.year, when.month, when.day, 7, tzinfo=UTC)
    return ActivityItem(uid(number), when, start, sport, minutes, rpe, load)


def comparison_of(
    workouts: list[PlannedItem],
    activities: list[ActivityItem],
    corrections: list[Correction] | None = None,
    today: date = LATER,
) -> Comparison:
    match = match_week(workouts, activities, corrections or [], today)
    return compare(workouts, activities, match)


def figures(comparison: Comparison, sport: str) -> Figures:
    return next(entry.figures for entry in comparison.sports if entry.sport == sport)


class TestFigures:
    def test_planned_against_actual_per_sport_and_in_all(self) -> None:
        result = comparison_of(
            [
                planned(1, 0, "running", 60),
                planned(2, 1, "cycling", 90),
                planned(3, 2, "running", 45),
            ],
            [
                performed(11, 0, "running", 50, rpe=6, load=300),
                performed(12, 1, "cycling", 100, rpe=5, load=500),
            ],
        )

        assert figures(result, "running") == Figures(
            planned_count=2,
            planned_minutes=105,
            actual_count=1,
            actual_minutes=50,
            load=300,
            rated_count=1,
        )
        assert figures(result, "cycling") == Figures(1, 90, 1, 100, 500, 1)
        assert result.total == Figures(3, 195, 2, 150, 800, 2)
        assert [entry.sport for entry in result.sports] == ["running", "cycling"]

    def test_a_session_nobody_planned_still_counts_as_training_done(self) -> None:
        result = comparison_of([planned(1, 0, "running", 60)], [performed(11, 3, "swimming", 40)])

        assert figures(result, "swimming") == Figures(0, 0, 1, 40, 0, 0)
        assert result.total.actual_minutes == 40

    def test_the_sports_come_in_a_fixed_order_and_only_when_involved(self) -> None:
        result = comparison_of(
            [planned(1, 0, "strength", 30)],
            [performed(11, 1, "other", 20), performed(12, 2, "cycling", 20)],
        )

        assert [entry.sport for entry in result.sports] == ["cycling", "strength", "other"]
        assert set(SPORT_ORDER) >= {entry.sport for entry in result.sports}

    def test_minutes_are_whole_minutes_rounded_half_up_and_the_total_adds_them_up(self) -> None:
        result = comparison_of(
            [],
            [performed(11, 0, "running", 10.5), performed(12, 1, "cycling", 10.5)],
        )

        assert figures(result, "running").actual_minutes == 11
        assert figures(result, "cycling").actual_minutes == 11
        assert result.total.actual_minutes == 22

    def test_an_activity_without_a_duration_counts_but_adds_no_minutes(self) -> None:
        result = comparison_of([planned(1)], [performed(11, minutes=None)])

        assert figures(result, "running").actual_count == 1
        assert figures(result, "running").actual_minutes == 0

    def test_the_load_is_the_sum_of_what_is_rated_and_the_count_says_how_many(self) -> None:
        result = comparison_of(
            [],
            [
                performed(11, 0, minutes=60, rpe=5, load=300),
                performed(12, 1, minutes=30, rpe=None, load=None),
                performed(13, 2, minutes=30, rpe=4, load=120),
            ],
        )

        assert (result.total.load, result.total.rated_count, result.total.actual_count) == (
            420,
            2,
            3,
        )

    def test_an_empty_week(self) -> None:
        result = comparison_of([], [])

        assert result.sports == ()
        assert result.total == Figures(0, 0, 0, 0, 0, 0)
        assert result.done_percent is None
        assert result.statuses == {status: 0 for status in Status}


class TestStatuses:
    def test_every_status_is_counted_also_at_zero(self) -> None:
        result = comparison_of(
            [
                planned(1, 0),
                planned(2, 1),
                planned(3, 2),
                planned(4, 3, "cycling"),
                planned(5, 12),  # a day that is not over
            ],
            [
                performed(11, 0),
                performed(12, 1, minutes=10),
                performed(13, 3, "swimming", 30),
            ],
            today=MONDAY + timedelta(days=5),
        )

        assert result.statuses == {
            Status.DONE: 1,
            Status.PARTIAL: 1,
            Status.MISSED: 1,
            Status.REPLACED: 1,
            Status.OPEN: 1,
        }

    @pytest.mark.parametrize(
        ("done", "missed", "percent"),
        [
            (0, 0, None),
            (0, 3, 0),
            (1, 2, 33),
            (2, 1, 67),
            (1, 1, 50),  # exactly half stays half
            (3, 0, 100),
            (1, 7, 13),  # 12.5 rounds up
        ],
    )
    def test_the_share_done_is_among_the_workouts_that_are_not_open(
        self, done: int, missed: int, percent: int | None
    ) -> None:
        workouts = [planned(n, day=n % 7, position=n // 7) for n in range(done + missed)]
        activities = [performed(100 + n, day=n % 7) for n in range(done)]

        assert comparison_of(workouts, activities).done_percent == percent

    def test_open_workouts_do_not_count_against_the_share(self) -> None:
        today = MONDAY + timedelta(days=2)
        result = comparison_of(
            [planned(1, 0), planned(2, 1), planned(3, 5)],
            [performed(11, 0)],
            today=today,
        )

        assert result.statuses[Status.OPEN] == 1
        assert result.done_percent == 50  # one of two that are judged
