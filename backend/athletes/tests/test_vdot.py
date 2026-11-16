import math
from typing import Any

import pytest

from athletes.vdot import DISTANCES, VDOT_MAX, VDOT_MIN, threshold_pace, vdot


def seconds(text: str) -> int:
    """``19:57`` or ``3:10:49`` as seconds."""
    parts = [int(part) for part in text.split(":")]
    total = 0
    for part in parts:
        total = total * 60 + part
    return total


class TestVdot:
    @pytest.mark.parametrize(
        ("distance", "time"),
        [("5k", "19:57"), ("10k", "41:21"), ("marathon", "3:10:49")],
    )
    def test_the_races_of_vdot_50_in_the_published_tables(self, distance: str, time: str) -> None:
        found = vdot(DISTANCES[distance], seconds(time))

        assert found == pytest.approx(50, abs=0.1)

    def test_a_faster_race_has_a_higher_vdot(self) -> None:
        slow, fast = (vdot(5000, seconds(time)) for time in ("25:00", "20:00"))

        assert slow is not None and fast is not None
        assert fast > slow

    def test_the_same_pace_over_a_longer_race_is_worth_more(self) -> None:
        # 4:00 per km: holding it for 10 km takes more than holding it for 5 km
        five, ten = vdot(5000, 5 * 240), vdot(10000, 10 * 240)

        assert five is not None and ten is not None
        assert ten > five

    def test_the_distances_are_these(self) -> None:
        assert DISTANCES == {
            "5k": 5000,
            "10k": 10000,
            "half_marathon": 21097.5,
            "marathon": 42195,
        }

    @pytest.mark.parametrize("bad", [0, -1, math.nan, math.inf, -math.inf, True, "5", None])
    def test_a_time_that_is_no_positive_number_has_no_vdot(self, bad: Any) -> None:
        assert vdot(5000, bad) is None

    @pytest.mark.parametrize("bad", [0, -5000, math.nan, math.inf, False, "5000", None])
    def test_a_distance_that_is_no_positive_number_has_no_vdot(self, bad: Any) -> None:
        assert vdot(bad, 1200) is None

    def test_the_range_is_what_a_runner_can_be(self) -> None:
        assert (VDOT_MIN, VDOT_MAX) == (20.0, 90.0)


class TestThresholdPace:
    @pytest.mark.parametrize(
        ("value", "pace"), [(30, 384), (40, 305.5), (50, 255), (60, 220), (70, 194)]
    )
    def test_the_pace_of_a_vdot(self, value: float, pace: float) -> None:
        assert threshold_pace(value) == pytest.approx(pace, abs=1)

    def test_vdot_50_is_about_4_15_per_kilometre(self) -> None:
        found = threshold_pace(50)

        assert found is not None
        assert divmod(round(found), 60) == (4, 15)

    def test_a_higher_vdot_has_a_faster_pace(self) -> None:
        found = [threshold_pace(value) for value in range(20, 91, 5)]
        paces = [pace for pace in found if pace is not None]

        assert len(paces) == len(found)
        assert paces == sorted(paces, reverse=True)

    def test_the_pace_stays_inside_what_a_threshold_can_be(self) -> None:
        # the same plausible range as the thresholds of the profile: 2:00 to 20:00 per km
        for value in (VDOT_MIN, VDOT_MAX):
            found = threshold_pace(value)
            assert found is not None
            assert 120 <= found <= 1200

    @pytest.mark.parametrize("bad", [0, -1, math.nan, math.inf, True, "50", None])
    def test_a_vdot_that_is_no_positive_number_has_no_pace(self, bad: Any) -> None:
        assert threshold_pace(bad) is None

    def test_the_vdot_of_a_race_gives_the_pace_of_its_form(self) -> None:
        found = vdot(5000, seconds("19:57"))
        assert found is not None

        pace = threshold_pace(found)

        assert pace == pytest.approx(255, abs=2)
