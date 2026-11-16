from datetime import date, timedelta
from typing import Any

import pytest

from season.skeleton import (
    MAX_WEEKS,
    ROLLING_WEEKS,
    Phase,
    Race,
    Skeleton,
    SkeletonInputs,
    build_skeleton,
    phase_weeks,
    phases,
    rolling_phases,
    taper_weeks,
    week_index,
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

        assert all(counts[phase] > 0 for phase in counts)

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


# --- the volume

MONDAY = date(2026, 11, 16)
assert MONDAY.weekday() == 0
BIG = 100_000  # a week that offers more than any test asks for


def weeks_from(count: int) -> date:
    """The Sunday that ends the ``count``-th week from ``MONDAY`` (1 is the first week)."""
    return MONDAY + timedelta(weeks=count) - timedelta(days=1)


def race(week: int, priority: str = "main", **fields: Any) -> Race:
    """A race on the Sunday of week ``week`` (0 is the first week)."""
    return Race(MONDAY + timedelta(weeks=week, days=6), priority, **fields)


def make(
    races: tuple[Race, ...] = (),
    *,
    capacity: int | list[int] = BIG,
    reference: int | None = 240,
    level: str = "normal",
    first: date = MONDAY,
) -> Skeleton:
    capacities = tuple([capacity] * MAX_WEEKS) if isinstance(capacity, int) else tuple(capacity)
    return build_skeleton(SkeletonInputs(first, capacities, races, reference, level))


def targets(skeleton: Skeleton) -> list[int]:
    return [week.target_minutes for week in skeleton.weeks]


def phase_list(skeleton: Skeleton) -> list[str]:
    return [week.phase.value for week in skeleton.weeks]


class TestTheHorizon:
    def test_without_a_race_it_is_twelve_weeks_of_base_and_build(self) -> None:
        skeleton = make()

        assert skeleton.rolling is True
        assert skeleton.main_race is None
        assert len(skeleton.weeks) == 12
        assert set(phase_list(skeleton)) == {"base", "build"}
        assert skeleton.truncated is False

    def test_it_runs_up_to_the_week_of_the_race(self) -> None:
        skeleton = make((race(9),))

        assert len(skeleton.weeks) == 10
        assert skeleton.weeks[-1].races == (race(9),)
        assert skeleton.weeks[-1].phase is Phase.TAPER
        assert skeleton.rolling is False

    def test_the_weeks_are_consecutive_mondays(self) -> None:
        skeleton = make((race(9),))

        assert [week.week_start for week in skeleton.weeks] == [
            MONDAY + timedelta(weeks=i) for i in range(10)
        ]
        assert all(week.week_start.weekday() == 0 for week in skeleton.weeks)

    def test_a_race_this_week_is_a_season_of_one_week(self) -> None:
        skeleton = make((race(0),))

        assert len(skeleton.weeks) == 1
        assert skeleton.weeks[0].phase is Phase.TAPER

    def test_a_race_that_is_over_is_left_out(self) -> None:
        old = Race(MONDAY - timedelta(days=3), "main")

        skeleton = make((old,))

        assert skeleton.rolling is True
        assert all(week.races == () for week in skeleton.weeks)

    def test_a_race_beyond_a_year_cuts_the_skeleton_off(self) -> None:
        skeleton = make((race(70),))

        assert len(skeleton.weeks) == MAX_WEEKS
        assert skeleton.truncated is True
        assert skeleton.main_race == race(70)
        assert all(week.phase is not Phase.TAPER for week in skeleton.weeks)

    def test_a_race_in_the_last_week_of_the_year_is_not_cut(self) -> None:
        skeleton = make((race(MAX_WEEKS - 1),))

        assert len(skeleton.weeks) == MAX_WEEKS
        assert skeleton.truncated is False
        assert skeleton.weeks[-1].phase is Phase.TAPER

    def test_the_main_race_is_the_a_race_else_the_latest_b_race(self) -> None:
        a = race(20, "main")
        b_before, b_after = race(10, "secondary"), race(30, "secondary")

        assert make((b_before, a)).main_race == a
        assert make((b_before, b_after)).main_race == b_after
        assert make((b_after, b_before)).main_race == b_after

    def test_a_c_race_alone_does_not_shape_the_season(self) -> None:
        c = race(5, "preparation")

        skeleton = make((c,))

        assert skeleton.rolling is True
        assert skeleton.weeks[5].races == (c,)

    def test_a_c_race_marks_its_week_and_changes_no_phase(self) -> None:
        a, c = race(20), race(8, "preparation")

        with_c, without = make((a, c)), make((a,))

        assert phase_list(with_c) == phase_list(without)
        assert targets(with_c) == targets(without)
        assert with_c.weeks[8].races == (c,)

    def test_two_races_of_a_week_are_both_listed_by_date(self) -> None:
        early = Race(MONDAY + timedelta(weeks=3, days=1), "preparation")
        late = Race(MONDAY + timedelta(weeks=3, days=5), "preparation")

        skeleton = make((late, early))

        assert skeleton.weeks[3].races == (early, late)

    def test_the_taper_follows_the_distance_of_the_main_race(self) -> None:
        short = make((race(12, distance_m=5_000, discipline="running"),))
        long = make((race(12, distance_m=42_195, discipline="running"),))

        assert phase_list(short).count("taper") == 1
        assert phase_list(long).count("taper") == 3


class TestTheStart:
    def test_the_first_week_is_the_reference_of_the_athlete(self) -> None:
        assert make((race(20),), reference=300).weeks[0].target_minutes == 300

    def test_without_a_reference_it_is_half_of_the_first_week(self) -> None:
        assert make((race(20),), reference=None, capacity=400).weeks[0].target_minutes == 200

    @pytest.mark.parametrize("reference", [None, 0, -5])
    def test_a_missing_or_empty_reference_counts_as_none(self, reference: int | None) -> None:
        assert make((race(20),), reference=reference, capacity=400).weeks[0].target_minutes == 200

    def test_the_start_is_at_least_an_hour(self) -> None:
        assert make((race(20),), reference=None, capacity=80).weeks[0].target_minutes == 60

    def test_the_first_week_with_time_decides_when_the_first_has_none(self) -> None:
        capacity = [0, 0, 400] + [400] * 49

        assert make((race(20),), reference=None, capacity=capacity).weeks[2].target_minutes == 200

    def test_with_no_time_at_all_every_target_is_zero(self) -> None:
        skeleton = make((race(20),), reference=None, capacity=0)

        assert set(targets(skeleton)) == {0}
        assert skeleton.peak_minutes == 0


class TestTheRamp:
    @pytest.mark.parametrize(
        ("level", "percent"), [("relaxed", 5), ("normal", 8), ("intensive", 10)]
    )
    def test_a_building_week_adds_the_percent_of_the_level(self, level: str, percent: int) -> None:
        skeleton = make((race(30),), reference=1000, level=level)

        first, second = targets(skeleton)[:2]
        assert first == 1000
        assert second == round(1000 * (1 + percent / 100))

    def test_an_unknown_level_counts_as_normal(self) -> None:
        assert targets(make((race(30),), level="furious")) == targets(make((race(30),)))

    def test_the_specific_phase_holds_the_level_it_reached(self) -> None:
        skeleton = make((race(30),), reference=300)

        specific = [w.target_minutes for w in skeleton.weeks if w.phase is Phase.SPECIFIC]
        held = [
            t
            for w, t in zip(skeleton.weeks, targets(skeleton), strict=True)
            if w.phase is Phase.SPECIFIC and not w.recovery
        ]
        assert len(specific) >= 2
        assert len(set(held)) == 1

    def test_the_volume_never_exceeds_the_best_week_on_offer(self) -> None:
        skeleton = make((race(30),), reference=300, capacity=350)

        assert max(targets(skeleton)) == 350
        assert skeleton.peak_minutes == 350

    def test_a_week_never_has_more_than_it_offers(self) -> None:
        capacity = [(i * 37) % 500 for i in range(MAX_WEEKS)]

        skeleton = make((race(30),), capacity=capacity, reference=300)

        for week, offered in zip(skeleton.weeks, capacity, strict=False):
            assert 0 <= week.target_minutes <= offered
            assert week.capacity_minutes == offered

    def test_a_week_without_time_is_zero_and_does_not_lose_the_level(self) -> None:
        capacity = [BIG, BIG, 0, BIG, BIG] + [BIG] * 47

        skeleton = make((race(30),), capacity=capacity, reference=1000)

        values = targets(skeleton)
        assert values[2] == 0
        # the empty week built nothing, but it counts for the cycle: week 3 is the recovery week
        assert values[3] == round(1080 * 0.65)
        assert values[4] == round(1000 * 1.08**2)  # and the build goes on from 1080

    def test_the_peak_is_the_highest_target(self) -> None:
        skeleton = make((race(30),), reference=250)

        assert skeleton.peak_minutes == max(targets(skeleton))

    def test_the_week_has_the_capacity_it_was_given_and_zero_beyond_the_list(self) -> None:
        skeleton = make((race(5),), capacity=[200, 200])

        assert [w.capacity_minutes for w in skeleton.weeks] == [200, 200, 0, 0, 0, 0]
        assert targets(skeleton)[2:] == [0, 0, 0, 0]


class TestTheRecoveryWeeks:
    def test_every_fourth_building_week_for_normal_and_intensive(self) -> None:
        for level in ("normal", "intensive"):
            skeleton = make((race(30),), level=level)

            found = [i for i, week in enumerate(skeleton.weeks) if week.recovery]
            assert found[:3] == [3, 7, 11], level

    def test_every_third_building_week_for_relaxed(self) -> None:
        skeleton = make((race(30),), level="relaxed")

        found = [i for i, week in enumerate(skeleton.weeks) if week.recovery]
        assert found[:4] == [2, 5, 8, 11]

    def test_a_recovery_week_is_65_percent_of_the_week_before(self) -> None:
        skeleton = make((race(30),), reference=1000)

        values = targets(skeleton)
        assert values[3] == round(values[2] * 0.65)

    def test_the_week_after_a_recovery_week_builds_on_the_one_before_it(self) -> None:
        values = targets(make((race(30),), reference=1000))

        assert values[4] == round(1000 * 1.08**3)

    def test_there_is_none_in_the_taper_nor_right_before_it(self) -> None:
        for weeks in range(4, 40):
            skeleton = make((race(weeks),))

            for index, week in enumerate(skeleton.weeks):
                if week.phase is Phase.TAPER:
                    assert not week.recovery
                if (
                    index + 1 < len(skeleton.weeks)
                    and skeleton.weeks[index + 1].phase is Phase.TAPER
                ):
                    assert not week.recovery

    def test_the_rolling_skeleton_has_them_too(self) -> None:
        skeleton = make()

        assert [i for i, week in enumerate(skeleton.weeks) if week.recovery] == [3, 7]


class TestTheTaperVolume:
    @pytest.mark.parametrize(
        ("distance", "percents"),
        [(5_000, (50,)), (21_100, (70, 45)), (42_195, (80, 65, 45))],
    )
    def test_the_taper_weeks_fall_to_these_shares_of_the_last_full_week(
        self, distance: int, percents: tuple[int, ...]
    ) -> None:
        skeleton = make((race(30, discipline="running", distance_m=distance),), reference=1000)

        full = [w.target_minutes for w in skeleton.weeks if w.phase is Phase.SPECIFIC][-1]
        taper = [w.target_minutes for w in skeleton.weeks if w.phase is Phase.TAPER]
        assert taper == [round(full * p / 100) for p in percents]

    def test_the_race_week_is_the_lowest_week_before_it(self) -> None:
        skeleton = make((race(30, discipline="running", distance_m=42_195),))

        values = targets(skeleton)
        assert values[-1] < values[-2] < values[-3] < values[-4]

    def test_a_taper_week_is_never_more_than_it_offers(self) -> None:
        skeleton = make((race(12),), capacity=100)

        assert all(t <= 100 for t in targets(skeleton))

    def test_a_season_that_is_all_taper_still_has_a_target(self) -> None:
        skeleton = make((race(1, discipline="running", distance_m=42_195),), reference=1000)

        assert phase_list(skeleton) == ["taper", "taper"]
        # a taper cut short to two weeks follows the two-week pattern (70 and 45 percent)
        assert targets(skeleton) == [700, 450]


class TestSeveralRaces:
    def test_a_b_race_before_the_main_race_gets_a_mini_taper(self) -> None:
        b = race(8, "secondary")

        with_b, without = make((race(20), b), reference=1000), make((race(20),), reference=1000)

        assert with_b.weeks[8].target_minutes == pytest.approx(
            without.weeks[8].target_minutes * 0.8, abs=1
        )
        assert phase_list(with_b) == phase_list(without)
        for index in range(len(without.weeks)):
            if index != 8:
                assert with_b.weeks[index].target_minutes == without.weeks[index].target_minutes

    def test_a_b_race_after_the_main_race_has_a_transition_and_a_build_of_its_own(self) -> None:
        main, later = race(10), race(22, "secondary")

        skeleton = make((main, later), reference=1000)

        phases_ = phase_list(skeleton)
        assert skeleton.main_race == main
        assert len(skeleton.weeks) == 23
        assert phases_[10] == "taper"
        assert phases_[11] == "transition"
        assert phases_[-1] == "taper"
        assert phases_[12:-1].count("taper") == 0
        assert "specific" in phases_[12:]

    def test_the_transition_week_is_half_of_the_last_full_week(self) -> None:
        skeleton = make((race(10), race(22, "secondary")), reference=1000, level="normal")

        full = [w.target_minutes for w in skeleton.weeks[:10] if not w.recovery][-1]
        assert skeleton.weeks[11].target_minutes == pytest.approx(full * 0.5, abs=1)
        assert skeleton.weeks[11].recovery is False

    def test_the_build_after_the_main_race_starts_at_80_percent_of_the_old_level(self) -> None:
        skeleton = make((race(10), race(30, "secondary")), reference=1000)

        full = [w.target_minutes for w in skeleton.weeks[:10] if not w.recovery][-1]
        assert skeleton.weeks[12].target_minutes == pytest.approx(full * 0.8, abs=1)

    def test_a_later_b_race_ends_with_its_own_taper(self) -> None:
        later = race(30, "secondary", discipline="running", distance_m=5_000)

        skeleton = make((race(10), later))

        assert phase_list(skeleton)[-1] == "taper"
        assert phase_list(skeleton)[-2] != "taper"

    def test_the_recovery_count_starts_again_after_the_transition(self) -> None:
        skeleton = make((race(10), race(30, "secondary")))

        found = [i for i, week in enumerate(skeleton.weeks) if week.recovery and i > 11]
        assert found[0] == 12 + 3

    def test_a_race_in_the_transition_week_only_marks_it(self) -> None:
        near = race(11, "secondary")

        skeleton = make((race(10), near))

        assert len(skeleton.weeks) == 11
        assert phase_list(skeleton)[-1] == "taper"

    def test_two_later_races_each_end_a_stretch(self) -> None:
        skeleton = make((race(10), race(20, "secondary"), race(30, "secondary")))

        assert len(skeleton.weeks) == 31
        assert phase_list(skeleton)[20] == "taper"
        assert phase_list(skeleton)[30] == "taper"
        assert phase_list(skeleton)[21] != "transition"

    def test_back_to_back_races_do_not_merge_their_tapers(self) -> None:
        skeleton = make((race(10), race(13, "secondary"), race(14, "secondary")), reference=1000)

        values = targets(skeleton)
        assert len(skeleton.weeks) == 15
        assert phase_list(skeleton)[13:] == ["taper", "taper"]
        # each is a one-week taper: half of its own level, not the end of a two-week taper
        assert values[13] == pytest.approx(values[14], abs=1)

    def test_an_a_race_with_an_earlier_b_race_and_a_later_one(self) -> None:
        skeleton = make((race(6, "secondary"), race(14), race(26, "secondary")))

        assert skeleton.main_race == race(14)
        assert len(skeleton.weeks) == 27


class TestEverySkeleton:
    @pytest.mark.parametrize("level", ["relaxed", "normal", "intensive"])
    @pytest.mark.parametrize("weeks", [0, 1, 2, 3, 5, 8, 13, 26, 51, 52, 80])
    @pytest.mark.parametrize("reference", [None, 90, 400])
    def test_the_invariants_hold(self, level: str, weeks: int, reference: int | None) -> None:
        capacity = [(i * 53) % 480 + 20 for i in range(MAX_WEEKS)]

        skeleton = make((race(weeks),), capacity=capacity, reference=reference, level=level)

        assert 1 <= len(skeleton.weeks) <= MAX_WEEKS
        for index, week in enumerate(skeleton.weeks):
            assert week.week_start == MONDAY + timedelta(weeks=index)
            assert 0 <= week.target_minutes <= week.capacity_minutes
        assert skeleton.peak_minutes == max(w.target_minutes for w in skeleton.weeks)
        assert skeleton.peak_minutes <= max(capacity)
        assert skeleton.weeks[-1].phase is Phase.TAPER or skeleton.truncated


class TestTheWeekIndex:
    def test_it_counts_calendar_weeks_from_the_first_monday(self) -> None:
        assert week_index(MONDAY, MONDAY) == 0
        assert week_index(MONDAY, MONDAY + timedelta(days=6)) == 0
        assert week_index(MONDAY, MONDAY + timedelta(days=7)) == 1
        assert week_index(MONDAY, MONDAY - timedelta(days=1)) == -1
        assert week_index(MONDAY, MONDAY - timedelta(days=7)) == -1
        assert week_index(MONDAY, MONDAY - timedelta(days=8)) == -2
