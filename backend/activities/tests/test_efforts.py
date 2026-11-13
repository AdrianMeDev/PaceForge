import math
import random
import time

import pytest

from activities.efforts import (
    MAX_POWER_W,
    POWER_WINDOWS,
    SPEED_WINDOWS,
    BestEfforts,
    Sample,
    best_efforts,
)


def ride(
    seconds: int, power: float = 200, heart_rate: float | None = 150, start: int = 0
) -> list[Sample]:
    return [Sample(start + s, power=power, heart_rate=heart_rate) for s in range(seconds)]


def run(
    seconds: int, speed: float, heart_rate: float | None = 160, start: int = 0, from_m: float = 0
) -> list[Sample]:
    return [
        Sample(start + s, distance=from_m + speed * s, heart_rate=heart_rate)
        for s in range(seconds + 1)
    ]


def test_the_windows_are_these() -> None:
    """Written out on purpose: other tests read the windows from the constants."""
    assert POWER_WINDOWS == (5, 60, 300, 1200, 3600)
    assert SPEED_WINDOWS == (300, 1200, 1800, 3600)


class TestPower:
    def test_negative_power_never_counts(self) -> None:
        assert best_efforts(ride(400, -50)).power == {}

    def test_a_weaker_later_stretch_does_not_replace_a_stronger_earlier_one(self) -> None:
        samples = ride(400, 300) + ride(400, 200, start=420)  # 20 s pause between

        assert best_efforts(samples).power[300].value == pytest.approx(300)

    def test_constant_power_fills_every_window_that_fits(self) -> None:
        found = best_efforts(ride(3600))

        assert set(found.power) == set(POWER_WINDOWS)
        assert all(effort.value == pytest.approx(200) for effort in found.power.values())
        assert found.speed == {}

    def test_a_hard_block_inside_a_longer_ride_is_found(self) -> None:
        samples = ride(600, 180) + ride(1200, 280, 170, start=600) + ride(600, 180, start=1800)

        found = best_efforts(samples)

        assert found.power[1200].value == pytest.approx(280)
        assert found.power[1200].heart_rate == pytest.approx(170)
        assert 3600 not in found.power  # 40 minutes are not an hour

    def test_the_best_window_may_straddle_two_blocks(self) -> None:
        samples = ride(100, 100) + ride(100, 300, start=100)

        assert best_efforts(samples).power[60].value == pytest.approx(300)
        assert best_efforts(samples).power[5].value == pytest.approx(300)

    def test_a_window_does_not_cross_a_pause(self) -> None:
        samples = ride(900, 250) + ride(900, 250, start=900 + 11)  # 11 s pause

        assert 1200 not in best_efforts(samples).power

    def test_a_short_gap_between_samples_is_bridged(self) -> None:
        samples = [Sample(s, power=250) for s in range(0, 1201, 10)]  # every 10 s

        assert best_efforts(samples).power[1200].value == pytest.approx(250)

    def test_a_window_does_not_cross_more_than_ten_seconds_without_power(self) -> None:
        missing = [Sample(900 + s, heart_rate=150) for s in range(12)]
        samples = ride(900) + missing + ride(900, start=912)

        assert 1200 not in best_efforts(samples).power
        assert best_efforts(samples).power[300].value == pytest.approx(200)

    def test_a_single_sample_without_power_is_bridged(self) -> None:
        samples = ride(900) + [Sample(900, heart_rate=150)] + ride(900, start=901)

        assert best_efforts(samples).power[1200].value == pytest.approx(200)

    @pytest.mark.parametrize("bad", [-5, 5001, math.nan, math.inf])
    def test_implausible_power_is_treated_as_missing(self, bad: float) -> None:
        glitches = [Sample(400 + s, power=bad) for s in range(12)]
        samples = ride(400) + glitches + ride(400, start=412)

        found = best_efforts(samples)

        assert found.power[300].value == pytest.approx(200)
        assert 1200 not in found.power
        assert all(effort.value <= MAX_POWER_W for effort in found.power.values())


class TestSpeed:
    def test_speed_comes_from_distance_over_time(self) -> None:
        found = best_efforts(run(1800, 10 / 3))  # 6000 m in 30 minutes

        assert found.speed[1800].value == pytest.approx(10 / 3)
        assert found.speed[1800].heart_rate == pytest.approx(160)
        assert set(found.speed) == {300, 1200, 1800}
        assert found.power == {}

    def test_the_fastest_part_is_found(self) -> None:
        samples = run(600, 3) + run(1200, 4, 175, start=601, from_m=1803)

        found = best_efforts(samples)

        assert found.speed[1200].value == pytest.approx(4)
        assert found.speed[1200].heart_rate == pytest.approx(175)

    def test_a_distance_that_falls_back_does_not_make_a_window_faster(self) -> None:
        samples = run(400, 3)
        samples[50] = Sample(50, distance=0)  # would make 350 s - 50 s look like 3.5 m/s

        assert best_efforts(samples).speed[300].value == pytest.approx(3)

    def test_distance_going_backwards_is_ignored(self) -> None:
        samples = run(400, 3)
        samples[200] = Sample(200, distance=10)

        assert best_efforts(samples).speed[300].value == pytest.approx(3)

    def test_missing_distances_inside_a_window_do_not_matter(self) -> None:
        samples = [
            sample if s % 3 == 0 else Sample(s, heart_rate=160)
            for s, sample in enumerate(run(400, 3))
        ]

        assert best_efforts(samples).speed[300].value == pytest.approx(3)

    def test_a_window_needs_a_measured_distance_at_both_ends(self) -> None:
        samples = run(400, 3)
        for second in (100, 200, 350):
            samples[second] = Sample(second, heart_rate=160)

        assert best_efforts(samples).speed[300].value == pytest.approx(3)

    def test_a_pause_still_ends_a_speed_window(self) -> None:
        samples = run(200, 3) + run(200, 3, start=212, from_m=603)

        assert 300 not in best_efforts(samples).speed

    def test_a_run_without_distance_has_no_speed_but_may_have_power(self) -> None:
        samples = [Sample(s, power=300, heart_rate=160) for s in range(400)]

        found = best_efforts(samples)

        assert found.speed == {}
        assert found.power[300].value == pytest.approx(300)


class TestHeartRate:
    def test_it_is_the_average_over_the_chosen_window(self) -> None:
        samples = [Sample(s, power=200, heart_rate=140 + (s % 2) * 20) for s in range(400)]

        assert best_efforts(samples).power[300].heart_rate == pytest.approx(150, abs=0.5)

    def test_missing_heart_rate_gives_none(self) -> None:
        assert best_efforts(ride(400, heart_rate=None)).power[300].heart_rate is None

    @pytest.mark.parametrize("bad", [0, 10, 260, -1])
    def test_implausible_heart_rate_is_left_out_of_the_average(self, bad: float) -> None:
        samples = ride(300, heart_rate=150)
        samples[10] = Sample(10, power=200, heart_rate=bad)

        assert best_efforts(samples).power[300].heart_rate == pytest.approx(150)


class TestRobustness:
    def test_no_samples_give_nothing(self) -> None:
        assert best_efforts([]) == BestEfforts()

    def test_too_short_an_activity_gives_only_the_windows_that_fit(self) -> None:
        assert set(best_efforts(ride(90)).power) == {5, 60}

    def test_unsorted_and_duplicate_samples_do_not_matter(self) -> None:
        samples = ride(400)
        shuffled = samples + samples[:50]
        random.Random(1).shuffle(shuffled)

        assert best_efforts(shuffled) == best_efforts(samples)

    @pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
    def test_a_sample_without_a_usable_time_is_skipped(self, bad: float) -> None:
        assert best_efforts([Sample(bad, power=200), *ride(10)]).power[5].value == pytest.approx(
            200
        )

    def test_a_long_activity_is_fast(self) -> None:
        samples = [
            Sample(s, power=200 + (s % 7), distance=3.0 * s, heart_rate=150) for s in range(100_000)
        ]

        began = time.perf_counter()
        found = best_efforts(samples)
        elapsed = time.perf_counter() - began

        assert set(found.power) == set(POWER_WINDOWS)
        assert set(found.speed) == set(SPEED_WINDOWS)
        assert elapsed < 1.0
