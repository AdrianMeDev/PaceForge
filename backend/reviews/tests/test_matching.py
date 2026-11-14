import random
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

import pytest

from reviews.matching import (
    PARTIAL_BELOW_PERCENT,
    ActivityItem,
    Correction,
    Origin,
    PlannedItem,
    Status,
    WeekMatch,
    WorkoutMatch,
    match_week,
)

MONDAY = date(2026, 11, 9)
TUESDAY = MONDAY + timedelta(days=1)
WEDNESDAY = MONDAY + timedelta(days=2)
THURSDAY = MONDAY + timedelta(days=3)
# A day that is over, with every workout of the week in the past, and one before the week.
LATER = MONDAY + timedelta(days=14)


def uid(number: int) -> UUID:
    return UUID(int=number)


def workout(
    number: int, day: date = MONDAY, sport: str = "running", minutes: int = 60, position: int = 0
) -> PlannedItem:
    return PlannedItem(uid(number), day, position, sport, minutes)


def activity(
    number: int,
    day: date = MONDAY,
    sport: str = "running",
    minutes: float | None = 60,
    hour: int = 7,
) -> ActivityItem:
    start = datetime(day.year, day.month, day.day, hour, tzinfo=UTC)
    return ActivityItem(uid(number), day, start, sport, minutes)


def result_of(match: WeekMatch, number: int) -> WorkoutMatch:
    return next(found for found in match.workouts if found.workout_id == uid(number))


class TestAutomaticMatch:
    def test_the_same_day_and_sport_belong_together(self) -> None:
        match = match_week([workout(1)], [activity(11)], [], LATER)
        assert match.workouts == (
            WorkoutMatch(uid(1), Status.DONE, Origin.AUTO, uid(11), Origin.AUTO),
        )
        assert match.unplanned == ()

    def test_another_day_or_sport_does_not_match_a_workout_of_a_day_still_to_come(self) -> None:
        today = MONDAY
        planned = [workout(1, TUESDAY)]
        match = match_week(
            planned, [activity(11, MONDAY), activity(12, TUESDAY, "cycling")], [], today
        )
        found = result_of(match, 1)
        assert found.activity_id is None
        assert found.status is Status.OPEN
        assert match.unplanned == (uid(11), uid(12))

    def test_two_sessions_of_one_sport_pair_up_in_order(self) -> None:
        planned = [workout(1, position=0), workout(2, position=1)]
        match = match_week(planned, [activity(12, hour=18), activity(11, hour=7)], [], LATER)
        assert result_of(match, 1).activity_id == uid(11)
        assert result_of(match, 2).activity_id == uid(12)

    def test_a_second_workout_without_a_second_activity_is_missed(self) -> None:
        planned = [workout(1, position=0), workout(2, position=1)]
        match = match_week(planned, [activity(11)], [], LATER)
        assert result_of(match, 1).status is Status.DONE
        assert result_of(match, 2).status is Status.MISSED
        assert result_of(match, 2).activity_id is None

    def test_an_extra_activity_is_not_planned(self) -> None:
        match = match_week([workout(1)], [activity(11), activity(12, hour=18)], [], LATER)
        assert result_of(match, 1).activity_id == uid(11)
        assert match.unplanned == (uid(12),)

    def test_an_activity_belongs_to_one_workout_only(self) -> None:
        planned = [workout(1, position=0), workout(2, position=1)]
        match = match_week(planned, [activity(11)], [], LATER)
        ids = [found.activity_id for found in match.workouts if found.activity_id]
        assert ids == [uid(11)]

    def test_the_result_does_not_depend_on_the_order_of_the_input(self) -> None:
        planned = [
            workout(1, MONDAY, position=0),
            workout(2, MONDAY, "cycling", position=1),
            workout(3, TUESDAY),
            workout(4, WEDNESDAY, "strength", 45),
        ]
        done = [
            activity(11, MONDAY, hour=8),
            activity(12, MONDAY, "cycling", 30, hour=17),
            activity(13, TUESDAY, "cycling"),
            activity(14, THURSDAY, "running"),
        ]
        corrections = [Correction(uid(4), no_activity=True), Correction(uid(3), status=Status.DONE)]
        expected = match_week(planned, done, corrections, LATER)
        shuffler = random.Random(1)
        for _ in range(20):
            shuffler.shuffle(planned)
            shuffler.shuffle(done)
            shuffler.shuffle(corrections)
            assert match_week(planned, done, corrections, LATER) == expected
        assert [found.workout_id for found in expected.workouts] == [uid(n) for n in (1, 2, 3, 4)]


class TestReplaced:
    def test_a_past_workout_takes_a_left_over_activity_of_its_day(self) -> None:
        match = match_week(
            [workout(1, sport="running")], [activity(11, sport="cycling")], [], LATER
        )
        found = result_of(match, 1)
        assert found.status is Status.REPLACED
        assert found.activity_id == uid(11)
        assert found.activity_origin is Origin.AUTO
        assert match.unplanned == ()

    def test_a_day_that_is_not_over_waits(self) -> None:
        match = match_week([workout(1, MONDAY)], [activity(11, sport="cycling")], [], MONDAY)
        assert result_of(match, 1).status is Status.OPEN
        assert match.unplanned == (uid(11),)

    def test_an_activity_of_the_right_sport_wins_over_replacing(self) -> None:
        planned = [workout(1, sport="running"), workout(2, sport="cycling", position=1)]
        match = match_week(planned, [activity(11, sport="cycling")], [], LATER)
        assert result_of(match, 2).status is Status.DONE
        assert result_of(match, 1).status is Status.MISSED

    def test_another_day_does_not_replace(self) -> None:
        match = match_week([workout(1, MONDAY)], [activity(11, TUESDAY, "cycling")], [], LATER)
        assert result_of(match, 1).status is Status.MISSED
        assert match.unplanned == (uid(11),)

    def test_an_activity_of_an_unknown_sport_can_replace(self) -> None:
        match = match_week([workout(1)], [activity(11, sport="other")], [], LATER)
        assert result_of(match, 1).status is Status.REPLACED


class TestStatus:
    @pytest.mark.parametrize(
        ("minutes", "status"),
        [
            (60, Status.DONE),
            (80, Status.DONE),
            (45, Status.DONE),  # exactly the limit
            (44.9, Status.PARTIAL),
            (1, Status.PARTIAL),
            (0, Status.PARTIAL),
        ],
    )
    def test_the_limit_is_three_quarters_of_the_planned_minutes(
        self, minutes: float, status: Status
    ) -> None:
        assert PARTIAL_BELOW_PERCENT == 75
        match = match_week([workout(1, minutes=60)], [activity(11, minutes=minutes)], [], LATER)
        assert result_of(match, 1).status is status

    def test_an_activity_without_a_duration_counts_as_done(self) -> None:
        match = match_week([workout(1)], [activity(11, minutes=None)], [], LATER)
        assert result_of(match, 1).status is Status.DONE

    def test_a_workout_without_an_activity_is_missed_after_its_day_and_open_until_then(
        self,
    ) -> None:
        planned = [workout(1, MONDAY), workout(2, TUESDAY), workout(3, WEDNESDAY)]
        match = match_week(planned, [], [], TUESDAY)
        assert [found.status for found in match.workouts] == [
            Status.MISSED,
            Status.OPEN,  # today: the day is not over
            Status.OPEN,
        ]
        assert all(found.status_origin is Origin.AUTO for found in match.workouts)

    def test_an_empty_week(self) -> None:
        assert match_week([], [], [], LATER) == WeekMatch((), ())
        assert match_week([], [activity(11)], [], LATER) == WeekMatch((), (uid(11),))


class TestCorrections:
    def test_the_user_links_another_activity(self) -> None:
        planned = [workout(1, MONDAY)]
        done = [activity(11, MONDAY), activity(12, TUESDAY, minutes=40)]
        match = match_week(planned, done, [Correction(uid(1), activity_id=uid(12))], LATER)
        found = result_of(match, 1)
        assert found.activity_id == uid(12)
        assert found.activity_origin is Origin.USER
        assert found.status is Status.PARTIAL  # worked out from the chosen activity
        assert found.status_origin is Origin.AUTO
        assert match.unplanned == (uid(11),)

    def test_a_linked_activity_is_not_taken_by_the_automatic_match(self) -> None:
        planned = [workout(1, MONDAY, position=0), workout(2, MONDAY, position=1)]
        done = [activity(11, hour=7), activity(12, hour=18)]
        match = match_week(planned, done, [Correction(uid(1), activity_id=uid(12))], LATER)
        assert result_of(match, 1).activity_id == uid(12)
        assert result_of(match, 2).activity_id == uid(11)

    def test_the_user_says_that_no_activity_belongs_to_a_workout(self) -> None:
        planned = [workout(1, position=0), workout(2, position=1)]
        done = [activity(11, hour=7)]
        match = match_week(planned, done, [Correction(uid(1), no_activity=True)], LATER)
        first, second = result_of(match, 1), result_of(match, 2)
        assert (first.activity_id, first.activity_origin) == (None, Origin.USER)
        assert first.status is Status.MISSED
        assert first.status_origin is Origin.AUTO  # missed because the day is over
        assert second.activity_id == uid(11)  # the activity goes to the next workout

    def test_no_activity_on_a_day_to_come_stays_open(self) -> None:
        match = match_week(
            [workout(1, TUESDAY)], [], [Correction(uid(1), no_activity=True)], MONDAY
        )
        assert result_of(match, 1).status is Status.OPEN

    @pytest.mark.parametrize("chosen", [Status.DONE, Status.PARTIAL, Status.REPLACED])
    def test_the_user_sets_the_status_of_a_workout_with_an_activity(self, chosen: Status) -> None:
        match = match_week([workout(1)], [activity(11)], [Correction(uid(1), status=chosen)], LATER)
        found = result_of(match, 1)
        assert (found.status, found.status_origin) == (chosen, Origin.USER)
        assert found.activity_id == uid(11)

    def test_a_status_that_describes_an_activity_is_ignored_without_one(self) -> None:
        match = match_week([workout(1)], [], [Correction(uid(1), status=Status.DONE)], LATER)
        found = result_of(match, 1)
        assert (found.status, found.status_origin) == (Status.MISSED, Origin.AUTO)

    def test_missed_frees_the_activity_for_the_next_workout(self) -> None:
        planned = [workout(1, position=0), workout(2, position=1)]
        match = match_week(
            planned, [activity(11)], [Correction(uid(1), status=Status.MISSED)], LATER
        )
        first, second = result_of(match, 1), result_of(match, 2)
        assert (first.status, first.status_origin, first.activity_id) == (
            Status.MISSED,
            Origin.USER,
            None,
        )
        assert second.activity_id == uid(11)
        assert second.status is Status.DONE

    def test_missed_is_allowed_for_a_day_that_is_not_over(self) -> None:
        match = match_week(
            [workout(1, TUESDAY)], [], [Correction(uid(1), status=Status.MISSED)], MONDAY
        )
        assert result_of(match, 1).status is Status.MISSED

    def test_open_cannot_be_chosen(self) -> None:
        match = match_week(
            [workout(1)], [activity(11)], [Correction(uid(1), status=Status.OPEN)], LATER
        )
        found = result_of(match, 1)
        assert (found.status, found.status_origin) == (Status.DONE, Origin.AUTO)

    def test_a_link_to_an_activity_that_is_not_there_falls_back_to_the_automatic_match(
        self,
    ) -> None:
        match = match_week(
            [workout(1)], [activity(11)], [Correction(uid(1), activity_id=uid(99))], LATER
        )
        found = result_of(match, 1)
        assert (found.activity_id, found.activity_origin) == (uid(11), Origin.AUTO)

    def test_an_activity_linked_to_two_workouts_belongs_to_the_first(self) -> None:
        planned = [workout(1, position=0), workout(2, position=1)]
        corrections = [
            Correction(uid(1), activity_id=uid(11)),
            Correction(uid(2), activity_id=uid(11)),
        ]
        match = match_week(planned, [activity(11)], corrections, LATER)
        assert result_of(match, 1).activity_id == uid(11)
        assert result_of(match, 2).activity_id is None
        assert result_of(match, 2).status is Status.MISSED

    def test_a_correction_of_a_workout_that_is_not_there_changes_nothing(self) -> None:
        expected = match_week([workout(1)], [activity(11)], [], LATER)
        corrections = [
            Correction(uid(99), no_activity=True),
            Correction(uid(98), activity_id=uid(11)),
        ]
        assert match_week([workout(1)], [activity(11)], corrections, LATER) == expected
