import pytest

from season.skeleton import (
    MAX_WEEKS,
    ROLLING_WEEKS,
    Phase,
    phase_weeks,
    phases,
    rolling_phases,
    taper_weeks,
)


class TestTheTaper:
    @pytest.mark.parametrize(
        ("discipline", "distance", "weeks"),
        [
            ("running", 5_000, 1),
            ("running", 10_000, 1),
            ("running", 10_001, 2),
            ("running", 21_097.5, 2),
            ("running", 21_100, 2),
            ("running", 21_101, 3),
            ("running", 42_195, 3),
            ("running", 100_000, 3),
            ("cycling", 40_000, 1),
            ("cycling", 100_000, 1),
            ("cycling", 100_001, 2),
            ("cycling", 200_000, 2),
            ("cycling", 200_001, 3),
            ("triathlon", 51_500, 1),
            ("triathlon", 51_501, 2),
            ("triathlon", 113_000, 2),
            ("triathlon", 226_000, 3),
        ],
    )
    def test_a_longer_race_has_a_longer_taper(
        self, discipline: str, distance: float, weeks: int
    ) -> None:
        assert taper_weeks(discipline, distance) == weeks

    @pytest.mark.parametrize(
        ("discipline", "distance"),
        [
            ("swimming", 3_800),
            ("running", None),
            (None, 42_195),
            ("rowing", 42_195),
            ("", 1_000),
            (None, None),
        ],
    )
    def test_swimming_no_distance_or_an_unknown_discipline_has_one_week(
        self, discipline: str | None, distance: float | None
    ) -> None:
        assert taper_weeks(discipline, distance) == 1


class TestThePhases:
    @pytest.mark.parametrize("taper", [0, 1, 2, 3])
    def test_every_week_has_exactly_one_phase(self, taper: int) -> None:
        for weeks in range(0, MAX_WEEKS + 1):
            result = phases(weeks, taper)

            assert len(result) == weeks
            assert sum(phase_weeks(weeks, taper).values()) == weeks

    @pytest.mark.parametrize("taper", [1, 2, 3])
    def test_the_taper_ends_the_stretch_in_the_race_week(self, taper: int) -> None:
        for weeks in range(taper, MAX_WEEKS + 1):
            result = phases(weeks, taper)

            assert result[-taper:] == (Phase.TAPER,) * taper
            assert Phase.TAPER not in result[:-taper]

    @pytest.mark.parametrize("taper", [0, 1, 2, 3])
    def test_the_phases_come_in_their_order(self, taper: int) -> None:
        order = list(Phase)
        for weeks in range(0, MAX_WEEKS + 1):
            ranks = [order.index(phase) for phase in phases(weeks, taper)]

            assert ranks == sorted(ranks)

    def test_a_long_preparation_has_all_four_phases(self) -> None:
        # 18 weeks before the taper: a quarter is 4.5, rounded half up 5; a third and a bit, 6
        assert phase_weeks(20, 2) == {
            Phase.BASE: 7,
            Phase.BUILD: 6,
            Phase.SPECIFIC: 5,
            Phase.TAPER: 2,
        }

    def test_the_longest_season_has_a_specific_phase_of_at_most_six_weeks(self) -> None:
        counts = phase_weeks(MAX_WEEKS, 3)

        assert counts[Phase.SPECIFIC] == 6
        assert counts[Phase.TAPER] == 3
        assert counts[Phase.BASE] > counts[Phase.BUILD]

    @pytest.mark.parametrize("weeks", range(9, 53))
    def test_the_specific_phase_is_between_two_and_six_weeks_when_there_is_time(
        self, weeks: int
    ) -> None:
        assert 2 <= phase_weeks(weeks, 3)[Phase.SPECIFIC] <= 6

    @pytest.mark.parametrize("weeks", [9, 10, 12, 26, 52])
    def test_with_time_every_phase_before_the_taper_is_there(self, weeks: int) -> None:
        counts = phase_weeks(weeks, 3)

        assert all(counts[phase] > 0 for phase in Phase)

    @pytest.mark.parametrize("before", [6, 7, 8, 10, 30])
    def test_six_weeks_before_the_taper_are_enough_for_a_base(self, before: int) -> None:
        assert phase_weeks(before + 2, 2)[Phase.BASE] > 0

    @pytest.mark.parametrize("before", [3, 4, 5])
    def test_below_six_weeks_before_the_taper_there_is_no_base(self, before: int) -> None:
        counts = phase_weeks(before + 2, 2)

        assert counts[Phase.BASE] == 0
        assert counts[Phase.BUILD] > 0
        assert counts[Phase.SPECIFIC] >= 2

    @pytest.mark.parametrize("before", [0, 1, 2])
    def test_below_three_weeks_before_the_taper_there_is_only_the_specific_phase(
        self, before: int
    ) -> None:
        counts = phase_weeks(before + 2, 2)

        assert counts[Phase.SPECIFIC] == before
        assert counts[Phase.BUILD] == counts[Phase.BASE] == 0

    def test_a_stretch_shorter_than_the_taper_is_all_taper(self) -> None:
        assert phases(2, 3) == (Phase.TAPER, Phase.TAPER)
        assert phases(1, 3) == (Phase.TAPER,)
        assert phases(0, 3) == ()

    def test_a_race_this_week_is_one_week_of_taper(self) -> None:
        assert phases(1, 1) == (Phase.TAPER,)

    def test_a_negative_number_of_weeks_or_taper_is_the_same_as_none(self) -> None:
        assert phases(-5, 2) == ()
        assert phases(5, -1) == phases(5, 0)

    def test_without_a_taper_the_season_ends_in_the_specific_phase(self) -> None:
        assert phases(10, 0)[-1] is Phase.SPECIFIC
        assert Phase.TAPER not in phases(10, 0)


class TestWithoutARace:
    def test_the_rolling_skeleton_is_twelve_weeks_of_base_then_build(self) -> None:
        result = rolling_phases()

        assert len(result) == ROLLING_WEEKS == 12
        assert result == (Phase.BASE,) * 6 + (Phase.BUILD,) * 6

    def test_it_has_no_taper_and_no_specific_phase(self) -> None:
        assert set(rolling_phases()) == {Phase.BASE, Phase.BUILD}

    @pytest.mark.parametrize("weeks", [0, 1, 5, 12, 52])
    def test_any_length_has_that_many_weeks(self, weeks: int) -> None:
        assert len(rolling_phases(weeks)) == weeks

    def test_the_limits_are_written_out_on_purpose(self) -> None:
        # The other tests read the constants and would follow a change.
        assert (MAX_WEEKS, ROLLING_WEEKS) == (52, 12)
