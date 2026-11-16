from datetime import date, timedelta
from typing import Any

import pytest

from athletes.vdot import DISTANCES, race_seconds, vdot
from goals import realism
from goals.realism import (
    AMBITIOUS_EXTRA_PERCENT,
    AMBITIOUS_EXTRA_VDOT,
    MODEL_MAX_M,
    MODEL_MIN_M,
    PREP_WEEKS,
    THRESHOLD_GAIN_MAX_PERCENT,
    THRESHOLD_GAIN_PERCENT_PER_WEEK,
    VDOT_GAIN_MAX,
    VDOT_GAIN_PER_WEEK,
    Assessment,
    Form,
    GoalFacts,
    Rating,
    Reason,
    assess,
    preparation_weeks,
    weeks_until,
)

TODAY = date(2027, 7, 12)


def in_weeks(weeks: int, extra_days: int = 0) -> date:
    return TODAY + timedelta(weeks=weeks, days=extra_days)


def race(weeks: int | None = 10, minutes_vdot: float | None = 52.0, **fields: Any) -> GoalFacts:
    """A 10 km run in ``weeks`` weeks, with the time that is worth ``minutes_vdot`` VDOT."""
    data: dict[str, Any] = {
        "kind": "race",
        "discipline": "running",
        "distance_m": 10_000.0,
        "target_time_seconds": None if minutes_vdot is None else race_seconds(10_000, minutes_vdot),
        "target_date": None if weeks is None else in_weeks(weeks),
        **fields,
    }
    return GoalFacts(**data)


def threshold(metric: str, value: float | None, weeks: int | None = 10) -> GoalFacts:
    return GoalFacts(
        kind="threshold",
        metric=metric,
        target_value=value,
        target_date=None if weeks is None else in_weeks(weeks),
    )


FORM = Form(vdot=50.0, ftp=240.0, threshold_pace=300.0)


class TestTheConstants:
    def test_they_are_these(self) -> None:
        assert (VDOT_GAIN_PER_WEEK, VDOT_GAIN_MAX, AMBITIOUS_EXTRA_VDOT) == (0.2, 5.0, 2.0)
        assert (THRESHOLD_GAIN_PERCENT_PER_WEEK, THRESHOLD_GAIN_MAX_PERCENT) == (0.5, 15.0)
        assert AMBITIOUS_EXTRA_PERCENT == 5.0
        assert (MODEL_MIN_M, MODEL_MAX_M) == (1500.0, 42195.0)
        assert PREP_WEEKS == ((5000.0, 4), (10000.0, 6), (21097.5, 10), (42195.0, 16))


class TestWeeksUntil:
    @pytest.mark.parametrize(
        ("days", "weeks"), [(0, 0), (6, 0), (7, 1), (13, 1), (14, 2), (70, 10), (71, 10)]
    )
    def test_whole_weeks_from_today(self, days: int, weeks: int) -> None:
        assert weeks_until(TODAY + timedelta(days=days), TODAY) == weeks

    def test_a_day_that_has_passed_or_none_is_none(self) -> None:
        assert weeks_until(TODAY - timedelta(days=1), TODAY) is None
        assert weeks_until(None, TODAY) is None


class TestPreparationWeeks:
    @pytest.mark.parametrize(
        ("distance", "weeks"),
        [
            (1500, 4),
            (5000, 4),
            (5001, 6),
            (10_000, 6),
            (10_001, 10),
            (21_097.5, 10),
            (21_098, 16),
            (42_195, 16),
        ],
    )
    def test_by_distance(self, distance: float, weeks: int) -> None:
        assert preparation_weeks(distance) == weeks

    @pytest.mark.parametrize("distance", [0, 1499, 42_196, 100_000])
    def test_a_distance_that_is_not_judged_has_none(self, distance: float) -> None:
        assert preparation_weeks(distance) is None


class TestARunningRace:
    def test_a_target_the_form_can_reach_is_realistic_and_stays_as_it_is(self) -> None:
        goal = race(10, 51.5)

        found = assess(goal, FORM, TODAY)

        assert found.rating is Rating.REALISTIC
        assert found.reason is None
        assert found.suggested == goal.target_time_seconds
        assert (found.current, found.weeks) == (50.0, 10)
        assert found.needed == pytest.approx(51.5, abs=0.1)

    def test_a_target_slower_than_the_form_is_realistic(self) -> None:
        assert assess(race(10, 40), FORM, TODAY).rating is Rating.REALISTIC

    def test_the_form_grows_by_a_fifth_of_a_vdot_a_week(self) -> None:
        # ten weeks make 52: 51.8 is realistic, 52.4 is not
        assert assess(race(10, 51.8), FORM, TODAY).rating is Rating.REALISTIC
        assert assess(race(10, 52.4), FORM, TODAY).rating is Rating.AMBITIOUS

    def test_the_growth_stops_at_five_vdot(self) -> None:
        far = in_weeks(200)

        assert assess(race(None, 54.8, target_date=far), FORM, TODAY).rating is Rating.REALISTIC
        assert assess(race(None, 55.4, target_date=far), FORM, TODAY).rating is Rating.AMBITIOUS

    def test_up_to_two_vdot_above_what_can_be_reached_is_ambitious(self) -> None:
        assert assess(race(10, 53.7), FORM, TODAY).rating is Rating.AMBITIOUS
        assert assess(race(10, 54.3), FORM, TODAY).rating is Rating.UNREALISTIC

    def test_it_suggests_the_time_the_form_can_reach_by_then(self) -> None:
        found = assess(race(10, 56), FORM, TODAY)

        assert found.rating is Rating.UNREALISTIC
        assert found.suggested is not None
        assert vdot(10_000, found.suggested) == pytest.approx(52.0, abs=0.1)
        assert found.suggested == race_seconds(10_000, 52.0)
        assert found.suggested > (race(10, 56).target_time_seconds or 0)

    def test_an_ambitious_target_gets_a_suggestion_too(self) -> None:
        found = assess(race(10, 53.2), FORM, TODAY)

        assert found.rating is Rating.AMBITIOUS
        assert found.suggested == race_seconds(10_000, 52.0)

    def test_the_race_today_has_no_time_to_grow(self) -> None:
        assert assess(race(0, 49.8), FORM, TODAY).rating is Rating.REALISTIC
        assert assess(race(0, 50.4), FORM, TODAY).rating is Rating.AMBITIOUS

    def test_the_numbers_are_rounded_to_one_decimal(self) -> None:
        found = assess(race(10, 51.5), Form(vdot=49.94), TODAY)

        assert found.current == 49.9
        assert found.needed == round(found.needed or 0, 1)


class TestWhatCannotBeJudged:
    @pytest.mark.parametrize("discipline", ["cycling", "swimming", "triathlon", ""])
    def test_another_discipline_has_no_model(self, discipline: str) -> None:
        found = assess(race(10, 52, discipline=discipline), FORM, TODAY)

        assert (found.rating, found.reason) == (Rating.UNKNOWN, Reason.NO_MODEL)
        assert (found.prep_weeks, found.prep_short) == (None, False)

    def test_a_general_goal_has_no_model(self) -> None:
        found = assess(GoalFacts(kind="general"), FORM, TODAY)

        assert (found.rating, found.reason) == (Rating.UNKNOWN, Reason.NO_MODEL)

    def test_a_race_without_a_target_time_has_no_target_but_still_a_preparation_check(self) -> None:
        found = assess(race(3, None), FORM, TODAY)

        assert (found.rating, found.reason) == (Rating.UNKNOWN, Reason.NO_TARGET)
        assert (found.prep_weeks, found.prep_short) == (6, True)

    def test_a_race_without_a_distance_has_no_target(self) -> None:
        found = assess(race(10, 52, distance_m=None), FORM, TODAY)

        assert (found.rating, found.reason) == (Rating.UNKNOWN, Reason.NO_TARGET)
        assert found.prep_weeks is None

    @pytest.mark.parametrize("distance", [1000.0, 50_000.0, 100_000.0])
    def test_a_distance_outside_the_model_is_out_of_range(self, distance: float) -> None:
        found = assess(race(10, 52, distance_m=distance, target_time_seconds=3600), FORM, TODAY)

        assert (found.rating, found.reason) == (Rating.UNKNOWN, Reason.OUT_OF_RANGE)
        assert found.prep_weeks is None

    def test_without_a_date_there_is_no_date(self) -> None:
        found = assess(race(None, 52), FORM, TODAY)

        assert (found.rating, found.reason, found.weeks) == (Rating.UNKNOWN, Reason.NO_DATE, None)

    def test_a_date_that_has_passed_is_no_date(self) -> None:
        found = assess(race(None, 52, target_date=TODAY - timedelta(days=1)), FORM, TODAY)

        assert (found.rating, found.reason) == (Rating.UNKNOWN, Reason.NO_DATE)
        assert found.prep_short is False

    def test_without_a_form_there_is_no_form_but_the_needed_vdot_is_told(self) -> None:
        found = assess(race(10, 52), Form(), TODAY)

        assert (found.rating, found.reason) == (Rating.UNKNOWN, Reason.NO_FORM)
        assert found.needed == pytest.approx(52, abs=0.1)
        assert found.current is None
        assert found.suggested is None

    def test_a_target_time_that_is_no_race_has_no_target(self) -> None:
        found = assess(race(10, 52, target_time_seconds=0), FORM, TODAY)

        assert (found.rating, found.reason) == (Rating.UNKNOWN, Reason.NO_TARGET)


class TestAShortPreparation:
    @pytest.mark.parametrize(
        ("distance", "weeks", "short"),
        [
            (5000.0, 3, True),
            (5000.0, 4, False),
            (10_000.0, 5, True),
            (10_000.0, 6, False),
            (21_097.5, 9, True),
            (21_097.5, 10, False),
            (42_195.0, 15, True),
            (42_195.0, 16, False),
        ],
    )
    def test_fewer_weeks_than_the_distance_needs_is_a_warning(
        self, distance: float, weeks: int, short: bool
    ) -> None:
        goal = race(weeks, None, distance_m=distance)

        found = assess(goal, FORM, TODAY)

        assert found.prep_short is short
        assert found.prep_weeks == preparation_weeks(distance)
        assert found.weeks == weeks

    def test_it_comes_with_a_rating_too(self) -> None:
        found = assess(race(2, 50.2), FORM, TODAY)

        assert found.rating is Rating.REALISTIC
        assert found.prep_short is True

    def test_the_marathon_distances_of_the_four_best_times_are_all_in_the_model(self) -> None:
        for distance in DISTANCES.values():
            assert preparation_weeks(distance) is not None


class TestAThresholdGoal:
    def test_ftp_up_to_the_gain_is_realistic(self) -> None:
        # ten weeks make 5 %: 240 W reach 252 W
        assert assess(threshold("ftp", 252), FORM, TODAY).rating is Rating.REALISTIC
        assert assess(threshold("ftp", 240), FORM, TODAY).rating is Rating.REALISTIC
        assert assess(threshold("ftp", 200), FORM, TODAY).rating is Rating.REALISTIC

    def test_ftp_up_to_five_points_more_is_ambitious_and_beyond_unrealistic(self) -> None:
        assert assess(threshold("ftp", 253), FORM, TODAY).rating is Rating.AMBITIOUS
        assert assess(threshold("ftp", 264), FORM, TODAY).rating is Rating.AMBITIOUS
        assert assess(threshold("ftp", 265), FORM, TODAY).rating is Rating.UNREALISTIC

    def test_the_gain_stops_at_fifteen_percent(self) -> None:
        far = threshold("ftp", 276, weeks=500)  # 240 W + 15 % = 276 W

        assert assess(far, FORM, TODAY).rating is Rating.REALISTIC
        assert assess(threshold("ftp", 277, weeks=500), FORM, TODAY).rating is Rating.AMBITIOUS

    def test_ftp_is_suggested_in_whole_watts(self) -> None:
        found = assess(threshold("ftp", 300), FORM, TODAY)

        assert (found.rating, found.suggested) == (Rating.UNREALISTIC, 252.0)
        assert (found.current, found.needed, found.weeks) == (240.0, 300, 10)

    def test_a_realistic_ftp_target_is_suggested_as_it_is(self) -> None:
        assert assess(threshold("ftp", 250), FORM, TODAY).suggested == 250

    def test_a_faster_threshold_pace_is_judged_on_the_speed(self) -> None:
        # ten weeks make 5 % of speed: 300 s/km become 285.7 s/km
        assert assess(threshold("threshold_pace", 290), FORM, TODAY).rating is Rating.REALISTIC
        assert assess(threshold("threshold_pace", 286), FORM, TODAY).rating is Rating.REALISTIC
        assert assess(threshold("threshold_pace", 280), FORM, TODAY).rating is Rating.AMBITIOUS
        assert assess(threshold("threshold_pace", 270), FORM, TODAY).rating is Rating.UNREALISTIC

    def test_the_pace_is_suggested_in_whole_seconds(self) -> None:
        found = assess(threshold("threshold_pace", 250), FORM, TODAY)

        assert (found.rating, found.suggested) == (Rating.UNREALISTIC, 286.0)

    def test_a_slower_pace_than_now_is_realistic(self) -> None:
        found = assess(threshold("threshold_pace", 320), FORM, TODAY)

        assert (found.rating, found.suggested) == (Rating.REALISTIC, 320)

    def test_the_form_of_the_other_threshold_does_not_count(self) -> None:
        assert (
            assess(threshold("ftp", 250), Form(threshold_pace=300), TODAY).reason is Reason.NO_FORM
        )
        assert (
            assess(threshold("threshold_pace", 290), Form(ftp=240), TODAY).reason is Reason.NO_FORM
        )

    def test_without_a_value_to_start_from_there_is_no_form(self) -> None:
        found = assess(threshold("ftp", 250), Form(), TODAY)

        assert (found.rating, found.reason, found.needed) == (Rating.UNKNOWN, Reason.NO_FORM, 250)

    def test_without_a_date_there_is_no_date(self) -> None:
        found = assess(threshold("ftp", 250, weeks=None), FORM, TODAY)

        assert (found.rating, found.reason) == (Rating.UNKNOWN, Reason.NO_DATE)

    def test_without_a_target_there_is_no_target(self) -> None:
        found = assess(threshold("ftp", None), FORM, TODAY)

        assert (found.rating, found.reason) == (Rating.UNKNOWN, Reason.NO_TARGET)

    def test_the_day_itself_has_no_time_to_grow(self) -> None:
        assert assess(threshold("ftp", 240, weeks=0), FORM, TODAY).rating is Rating.REALISTIC
        assert assess(threshold("ftp", 245, weeks=0), FORM, TODAY).rating is Rating.AMBITIOUS

    def test_a_threshold_goal_has_no_preparation_warning(self) -> None:
        found = assess(threshold("ftp", 250, weeks=1), FORM, TODAY)

        assert (found.prep_short, found.prep_weeks) == (False, None)


class TestThePureModule:
    def test_the_same_goal_and_form_give_the_same_judgement(self) -> None:
        assert assess(race(10, 53), FORM, TODAY) == assess(race(10, 53), FORM, TODAY)

    def test_it_needs_neither_the_database_nor_django(self) -> None:
        source = open(realism.__file__).read()

        assert "django" not in source.lower().replace("no django", "")
        assert "objects" not in source

    def test_a_judgement_is_a_frozen_value(self) -> None:
        found = assess(race(10, 53), FORM, TODAY)

        with pytest.raises(AttributeError):
            found.rating = Rating.REALISTIC  # type: ignore[misc]
        assert isinstance(found, Assessment)
