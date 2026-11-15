from typing import Any

import pytest

from availability.intensity import (
    DEFAULT_LEVEL,
    LEVEL_LIMITS,
    LIMIT_NAMES,
    LIMIT_RANGES,
    IntensityLevel,
    Limits,
    effective_limits,
    limit_problems,
    range_message,
)


class TestLevels:
    def test_the_levels_and_their_limits_are_the_decided_ones(self) -> None:
        assert LEVEL_LIMITS == {
            IntensityLevel.RELAXED: Limits(1, 115, 130, 85),
            IntensityLevel.NORMAL: Limits(2, 120, 140, 80),
            IntensityLevel.INTENSIVE: Limits(3, 130, 150, 75),
        }

    def test_normal_is_the_default(self) -> None:
        assert DEFAULT_LEVEL is IntensityLevel.NORMAL

    def test_the_values_are_the_ones_stored(self) -> None:
        assert IntensityLevel.values == ["relaxed", "normal", "intensive"]

    @pytest.mark.parametrize("level", list(IntensityLevel))
    def test_every_level_lies_within_the_ranges_of_own_values(self, level: IntensityLevel) -> None:
        limits = LEVEL_LIMITS[level]
        for name in LIMIT_NAMES:
            low, high = LIMIT_RANGES[name]
            assert low <= getattr(limits, name) <= high, (level, name)
        assert limits.progression_warning_percent < limits.progression_error_percent

    def test_a_harder_level_allows_more_in_every_limit(self) -> None:
        relaxed, normal, intensive = (LEVEL_LIMITS[level] for level in IntensityLevel)
        for name in ("max_hard_days", "progression_warning_percent", "progression_error_percent"):
            assert getattr(relaxed, name) < getattr(normal, name) < getattr(intensive, name)
        assert relaxed.easy_share_percent > normal.easy_share_percent > intensive.easy_share_percent

    def test_every_limit_has_a_range(self) -> None:
        assert set(LIMIT_RANGES) == set(LIMIT_NAMES)
        assert LIMIT_NAMES == (
            "max_hard_days",
            "progression_warning_percent",
            "progression_error_percent",
            "easy_share_percent",
        )


class TestEffectiveLimits:
    @pytest.mark.parametrize("level", list(IntensityLevel))
    def test_without_own_values_they_are_the_levels(self, level: IntensityLevel) -> None:
        assert effective_limits(level, {}) == LEVEL_LIMITS[level]
        assert effective_limits(level.value, dict.fromkeys(LIMIT_NAMES)) == LEVEL_LIMITS[level]

    @pytest.mark.parametrize(
        ("name", "value"),
        [
            ("max_hard_days", 0),
            ("progression_warning_percent", 110),
            ("progression_error_percent", 200),
            ("easy_share_percent", 90),
        ],
    )
    def test_an_own_value_replaces_only_its_own_limit(self, name: str, value: int) -> None:
        limits = effective_limits("normal", {name: value})
        for other in LIMIT_NAMES:
            expected = value if other == name else getattr(LEVEL_LIMITS[DEFAULT_LEVEL], other)
            assert getattr(limits, other) == expected, other

    def test_all_own_values_together(self) -> None:
        own = {
            "max_hard_days": 4,
            "progression_warning_percent": 105,
            "progression_error_percent": 110,
            "easy_share_percent": 50,
        }
        assert effective_limits("relaxed", own) == Limits(4, 105, 110, 50)

    def test_an_unknown_level_is_refused(self) -> None:
        with pytest.raises(ValueError):
            effective_limits("brutal", {})

    def test_an_unknown_limit_is_refused(self) -> None:
        with pytest.raises(ValueError):
            effective_limits("normal", {"rest_days": 1})


class TestLimitProblems:
    def test_no_own_values_are_fine(self) -> None:
        assert limit_problems("normal", {}) == {}
        assert limit_problems("normal", dict.fromkeys(LIMIT_NAMES)) == {}

    @pytest.mark.parametrize("name", LIMIT_NAMES)
    def test_both_ends_of_a_range_are_fine(self, name: str) -> None:
        low, high = LIMIT_RANGES[name]
        # The other progression limit is set so that the order of the two holds at both ends.
        partner = {
            "progression_warning_percent": {"progression_error_percent": 300},
            "progression_error_percent": {"progression_warning_percent": 100},
        }.get(name, {})
        if name == "progression_error_percent":
            low += 1  # 100 cannot be above a warning limit of at least 100
        assert limit_problems("normal", {name: low, **partner}) == {}
        assert limit_problems("normal", {name: high, **partner}) == {}

    @pytest.mark.parametrize("name", LIMIT_NAMES)
    def test_just_outside_a_range_is_a_problem(self, name: str) -> None:
        low, high = LIMIT_RANGES[name]
        assert limit_problems("normal", {name: low - 1}) == {name: range_message(name)}
        assert limit_problems("normal", {name: high + 1}) == {name: range_message(name)}

    @pytest.mark.parametrize("value", [True, False, 2.0, "2", [2]])
    def test_only_whole_numbers_are_values(self, value: Any) -> None:
        assert limit_problems("normal", {"max_hard_days": value}) == {
            "max_hard_days": range_message("max_hard_days")
        }

    def test_the_messages_say_the_range(self) -> None:
        assert range_message("max_hard_days") == "Enter a whole number of days between 0 and 4."
        assert range_message("easy_share_percent") == "Enter a whole percent between 50 and 100."
        assert range_message("progression_error_percent") == (
            "Enter a whole percent between 100 and 300."
        )

    def test_a_warning_at_or_above_the_error_is_told_at_the_error_if_both_are_own(self) -> None:
        for warning in (150, 160):
            assert limit_problems(
                "normal",
                {"progression_warning_percent": warning, "progression_error_percent": 150},
            ) == {
                "progression_error_percent": (
                    f"The warning limit ({warning} %) must be below the error limit (150 %)."
                )
            }

    def test_an_own_warning_against_the_levels_error_is_told_at_the_warning(self) -> None:
        # normal: error 140
        assert limit_problems("normal", {"progression_warning_percent": 140}) == {
            "progression_warning_percent": (
                "The warning limit (140 %) must be below the error limit (140 %)."
            )
        }
        assert limit_problems("normal", {"progression_warning_percent": 139}) == {}

    def test_an_own_error_against_the_levels_warning_is_told_at_the_error(self) -> None:
        # intensive: warning 130
        assert limit_problems("intensive", {"progression_error_percent": 130}) == {
            "progression_error_percent": (
                "The warning limit (130 %) must be below the error limit (130 %)."
            )
        }
        assert limit_problems("intensive", {"progression_error_percent": 131}) == {}

    def test_the_order_depends_on_the_level(self) -> None:
        own = {"progression_warning_percent": 135}
        assert limit_problems("normal", own) == {}  # error 140
        assert "progression_warning_percent" in limit_problems("relaxed", own)  # error 130

    def test_ranges_are_told_before_the_order(self) -> None:
        own = {"progression_warning_percent": 250, "progression_error_percent": 120}
        assert limit_problems("normal", own) == {
            "progression_warning_percent": range_message("progression_warning_percent")
        }

    def test_an_unknown_limit_is_refused(self) -> None:
        with pytest.raises(ValueError):
            limit_problems("normal", {"rest_days": 1})
