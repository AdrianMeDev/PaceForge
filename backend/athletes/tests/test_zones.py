import math

import pytest

from athletes.zones import (
    Zone,
    ZoneSet,
    heart_rate_zones,
    pace_zones,
    power_zones,
)


def bounds(zone_set: ZoneSet | None) -> list[tuple[int | None, int | None]]:
    assert zone_set is not None
    return [(zone.lower, zone.upper) for zone in zone_set.zones]


class TestPower:
    def test_exact_bounds_for_an_ftp_of_250(self) -> None:
        # 55, 75, 90, 105, 120 and 150 percent; .5 rounds up
        assert bounds(power_zones(250)) == [
            (None, 138),
            (138, 188),
            (188, 225),
            (225, 263),
            (263, 300),
            (300, 375),
            (375, None),
        ]

    def test_seven_named_zones_in_watts(self) -> None:
        zone_set = power_zones(250)

        assert zone_set is not None
        assert zone_set.basis == "ftp"
        assert [zone.number for zone in zone_set.zones] == [1, 2, 3, 4, 5, 6, 7]
        assert [zone.name for zone in zone_set.zones] == [
            "Active recovery",
            "Endurance",
            "Tempo",
            "Threshold",
            "VO2max",
            "Anaerobic capacity",
            "Neuromuscular power",
        ]
        assert {zone.unit for zone in zone_set.zones} == {"W"}

    def test_half_a_watt_rounds_up(self) -> None:
        # 333 W: 150 percent is 499.5, 55 percent is 183.15
        assert bounds(power_zones(333)) == [
            (None, 183),
            (183, 250),
            (250, 300),
            (300, 350),
            (350, 400),
            (400, 500),
            (500, None),
        ]

    def test_a_fractional_ftp_works(self) -> None:
        assert bounds(power_zones(262.4))[0] == (None, 144)


class TestHeartRate:
    def test_exact_bounds_from_the_lactate_threshold(self) -> None:
        # 85, 90, 95 and 100 percent of 165
        assert bounds(heart_rate_zones(lthr=165)) == [
            (None, 140),
            (140, 149),
            (149, 157),
            (157, 165),
            (165, None),
        ]

    def test_five_named_zones_in_beats(self) -> None:
        zone_set = heart_rate_zones(lthr=165)

        assert zone_set is not None
        assert zone_set.basis == "lthr"
        assert [zone.name for zone in zone_set.zones] == [
            "Recovery",
            "Aerobic",
            "Tempo",
            "Sub-threshold",
            "Super-threshold",
        ]
        assert {zone.unit for zone in zone_set.zones} == {"bpm"}

    def test_exact_bounds_from_the_maximum_if_there_is_no_threshold(self) -> None:
        # 60, 70, 80 and 90 percent of 190
        assert bounds(heart_rate_zones(max_hr=190)) == [
            (None, 114),
            (114, 133),
            (133, 152),
            (152, 171),
            (171, None),
        ]

    def test_the_basis_says_which_threshold_was_used(self) -> None:
        only_max = heart_rate_zones(max_hr=190)

        assert only_max is not None
        assert only_max.basis == "max_hr"
        assert [zone.name for zone in only_max.zones][0] == "Very light"

    def test_the_lactate_threshold_is_preferred_over_the_maximum(self) -> None:
        both = heart_rate_zones(lthr=165, max_hr=190)

        assert both == heart_rate_zones(lthr=165)
        assert both != heart_rate_zones(max_hr=190)

    def test_an_unusable_threshold_falls_back_to_the_maximum(self) -> None:
        assert heart_rate_zones(lthr=0, max_hr=190) == heart_rate_zones(max_hr=190)
        assert heart_rate_zones(lthr=None, max_hr=190) == heart_rate_zones(max_hr=190)


class TestPace:
    def test_exact_bounds_for_a_threshold_pace_of_300(self) -> None:
        # 129, 114, 106 and 99 percent of 300 s/km; slow to fast, so the bounds fall
        assert bounds(pace_zones(300)) == [
            (387, None),
            (342, 387),
            (318, 342),
            (297, 318),
            (None, 297),
        ]

    def test_five_named_zones_in_seconds_per_kilometre(self) -> None:
        zone_set = pace_zones(300)

        assert zone_set is not None
        assert zone_set.basis == "threshold_pace"
        assert [zone.name for zone in zone_set.zones] == [
            "Recovery",
            "Aerobic",
            "Tempo",
            "Threshold",
            "Interval",
        ]
        assert {zone.unit for zone in zone_set.zones} == {"s/km"}

    def test_the_threshold_pace_lies_inside_the_threshold_zone(self) -> None:
        zone = pace_zones(300).zones[3]  # type: ignore[union-attr]

        assert zone.lower is not None and zone.upper is not None
        assert zone.lower <= 300 < zone.upper


@pytest.mark.parametrize(
    "zone_set",
    [
        power_zones(250),
        power_zones(333),
        heart_rate_zones(lthr=165),
        heart_rate_zones(max_hr=190),
    ],
)
def test_rising_zones_are_contiguous_and_open_at_both_ends(zone_set: ZoneSet | None) -> None:
    assert zone_set is not None
    zones = zone_set.zones
    assert zones[0].lower is None
    assert zones[-1].upper is None
    for below, above in zip(zones, zones[1:], strict=False):
        assert below.upper is not None
        assert below.upper == above.lower
        assert below.upper > (below.lower or 0)


@pytest.mark.parametrize("pace", [300, 241, 333.3, 150, 1200])
def test_pace_zones_are_contiguous_and_open_at_both_ends(pace: float) -> None:
    zone_set = pace_zones(pace)

    assert zone_set is not None
    zones = zone_set.zones
    assert zones[0].upper is None
    assert zones[-1].lower is None
    for slower, faster in zip(zones, zones[1:], strict=False):
        assert slower.lower is not None
        assert slower.lower == faster.upper
        if slower.upper is not None:
            assert slower.lower < slower.upper


@pytest.mark.parametrize("value", [None, 0, -1, -250.5, math.nan, math.inf, -math.inf, "250", True])
def test_an_unusable_threshold_gives_no_zones(value: object) -> None:
    assert power_zones(value) is None  # type: ignore[arg-type]
    assert heart_rate_zones(lthr=value) is None  # type: ignore[arg-type]
    assert heart_rate_zones(max_hr=value) is None  # type: ignore[arg-type]
    assert pace_zones(value) is None  # type: ignore[arg-type]


def test_no_threshold_at_all_gives_no_zones() -> None:
    assert heart_rate_zones() is None


def test_zones_are_values_that_cannot_be_changed() -> None:
    zone = Zone(1, "Easy", None, 100, "W")

    with pytest.raises(AttributeError):
        zone.upper = 5  # type: ignore[misc]
