import dataclasses
import random
from datetime import date, timedelta
from fractions import Fraction
from typing import Any

import pytest

from availability.intensity import LEVEL_LIMITS, IntensityLevel, Limits
from planning import rules
from planning.context import PlanContext
from planning.rules import (
    ALL_CHECKS,
    BASIC_CHECKS,
    EASY_UP_TO_ZONE,
    HARD_FROM_ZONE,
    MAX_WORKOUTS_PER_DAY,
    RHYTHM_CHECKS,
    Finding,
    Intensity,
    Severity,
    check_a_free_day,
    check_double_days,
    check_duplicates,
    check_easy_share,
    check_hard_days,
    check_hard_days_in_a_row,
    check_progression,
    check_times_of_day,
    check_workouts_per_day,
    easy_minutes,
    intensity_of,
)
from planning.schema import (
    Goal,
    Segment,
    SegmentKind,
    Slot,
    Sport,
    WeekPlan,
    Workout,
    ZoneSystem,
)

MONDAY = date(2027, 7, 12)
assert MONDAY.weekday() == 0

# Most tests here use the limits of "intensive" (3 hard days, 130 and 150 %), which were the fixed
# limits before there were levels; ``TestTheLimitsOfTheContext`` covers the others.
INTENSIVE = LEVEL_LIMITS[IntensityLevel.INTENSIVE]


def day(offset: int) -> date:
    return MONDAY + timedelta(days=offset)


def workout(offset: int = 1, minutes: int = 60, **fields: Any) -> Workout:
    data: dict[str, Any] = {
        "day": day(offset),
        "sport": Sport.CYCLING,
        "title": "Ride",
        "goal": Goal.ENDURANCE,
        "duration_minutes": minutes,
        **fields,
    }
    return Workout(**data)


def hard(offset: int = 1, minutes: int = 60, **fields: Any) -> Workout:
    return workout(offset, minutes, goal=Goal.THRESHOLD, **fields)


def week(*workouts: Workout) -> WeekPlan:
    return WeekPlan(MONDAY, tuple(workouts))


def context(**fields: Any) -> PlanContext:
    data: dict[str, Any] = {
        "week_start": MONDAY,
        "minutes": (600,) * 7,
        "absences": (None,) * 7,
        "weekly_budget": None,
        "weekly_minutes": 4200,
        "zone_systems": frozenset(),
        "recent_weeks": (),
        "limits": INTENSIVE,
        **fields,
    }
    return PlanContext(**data)


class TestHowHardAWorkoutIs:
    @pytest.mark.parametrize("goal", [Goal.THRESHOLD, Goal.VO2MAX])
    def test_the_goals_threshold_and_vo2max_are_hard_whatever_the_zone(self, goal: Goal) -> None:
        assert intensity_of(workout(goal=goal)) is Intensity.HARD
        assert (
            intensity_of(workout(goal=goal, zone_system=ZoneSystem.POWER, zone=1)) is Intensity.HARD
        )

    @pytest.mark.parametrize(
        ("zone", "expected"),
        [
            (1, Intensity.EASY),
            (2, Intensity.EASY),
            (3, Intensity.MODERATE),
            (4, Intensity.HARD),
            (5, Intensity.HARD),
            (6, Intensity.HARD),
            (7, Intensity.HARD),
        ],
    )
    @pytest.mark.parametrize("system", list(ZoneSystem))
    def test_the_zone_of_the_whole_workout_decides(
        self, system: ZoneSystem, zone: int, expected: Intensity
    ) -> None:
        assert intensity_of(workout(zone_system=system, zone=zone)) is expected

    @pytest.mark.parametrize(
        "goal", [Goal.RECOVERY, Goal.ENDURANCE, Goal.TEMPO, Goal.STRENGTH, Goal.OTHER]
    )
    def test_without_a_zone_the_other_goals_are_easy(self, goal: Goal) -> None:
        assert intensity_of(workout(goal=goal)) is Intensity.EASY

    def test_the_highest_zone_of_the_segments_decides(self) -> None:
        segments = (
            Segment(SegmentKind.WARMUP, 600, 1, ZoneSystem.POWER, 1),
            Segment(SegmentKind.WORK, 300, 4, ZoneSystem.POWER, 4),
            Segment(SegmentKind.RECOVERY, 120, 4, ZoneSystem.POWER, 1),
        )

        assert intensity_of(workout(segments=segments)) is Intensity.HARD

    def test_a_workout_of_easy_segments_is_easy_and_of_moderate_ones_moderate(self) -> None:
        easy = (Segment(SegmentKind.STEADY, 3600, 1, ZoneSystem.POWER, 2),)
        moderate = (Segment(SegmentKind.STEADY, 3600, 1, ZoneSystem.POWER, 3),)

        assert intensity_of(workout(segments=easy)) is Intensity.EASY
        assert intensity_of(workout(segments=moderate)) is Intensity.MODERATE

    def test_a_hard_zone_in_the_session_or_in_a_segment_is_enough(self) -> None:
        easy_segment = (Segment(SegmentKind.STEADY, 3600, 1, ZoneSystem.POWER, 1),)

        assert (
            intensity_of(workout(zone_system=ZoneSystem.POWER, zone=5, segments=easy_segment))
            is Intensity.HARD
        )

    def test_segments_without_a_zone_do_not_count(self) -> None:
        assert intensity_of(workout(segments=(Segment(SegmentKind.WORK, 3600),))) is Intensity.EASY

    def test_the_limits_are_the_documented_ones(self) -> None:
        assert (HARD_FROM_ZONE, EASY_UP_TO_ZONE) == (4, 2)
        assert MAX_WORKOUTS_PER_DAY == 2
        assert (INTENSIVE.max_hard_days, INTENSIVE.progression_warning_percent) == (3, 130)
        assert INTENSIVE.progression_error_percent == 150


class TestTooManyHardDays:
    def test_three_hard_days_are_fine(self) -> None:
        assert check_hard_days(week(hard(0), hard(2), hard(4)), context()) == []

    def test_four_hard_days_are_an_error(self) -> None:
        plan = week(hard(0), hard(2), hard(4), hard(6))

        assert check_hard_days(plan, context()) == [
            Finding(
                Severity.ERROR,
                "too_many_hard_days",
                "The week has 4 hard days; your intensity settings allow at most 3.",
                "workouts",
            )
        ]

    def test_a_day_counts_once_however_many_hard_workouts_it_has(self) -> None:
        plan = week(hard(0), hard(0), hard(0), hard(2), hard(4))

        assert check_hard_days(plan, context()) == []

    def test_easy_workouts_do_not_count(self) -> None:
        plan = week(hard(0), hard(2), hard(4), workout(5), workout(6), workout(1))

        assert check_hard_days(plan, context()) == []

    def test_workouts_outside_the_week_do_not_count(self) -> None:
        plan = week(hard(0), hard(2), hard(4), hard(8), hard(-1))

        assert check_hard_days(plan, context()) == []


class TestTheLimitsOfTheContext:
    """The hard days and the progression limits are those of the athlete's level or own values."""

    @staticmethod
    def limits(level: IntensityLevel, **own: int) -> Limits:
        return dataclasses.replace(LEVEL_LIMITS[level], **own)

    def test_a_context_without_limits_has_those_of_normal(self) -> None:
        bare = PlanContext(
            week_start=MONDAY,
            minutes=(600,) * 7,
            absences=(None,) * 7,
            weekly_budget=None,
            weekly_minutes=4200,
            zone_systems=frozenset(),
            recent_weeks=(),
        )

        assert bare.limits == LEVEL_LIMITS[IntensityLevel.NORMAL]

    @pytest.mark.parametrize(
        ("level", "allowed"),
        [(IntensityLevel.RELAXED, 1), (IntensityLevel.NORMAL, 2), (IntensityLevel.INTENSIVE, 3)],
    )
    def test_each_level_allows_its_number_of_hard_days(
        self, level: IntensityLevel, allowed: int
    ) -> None:
        ctx = context(limits=LEVEL_LIMITS[level])
        days = [0, 2, 4, 6]

        assert check_hard_days(week(*(hard(d) for d in days[:allowed])), ctx) == []
        found = check_hard_days(week(*(hard(d) for d in days[: allowed + 1])), ctx)
        assert [f.code for f in found] == ["too_many_hard_days"]
        assert found[0].message.endswith(f"allow at most {allowed}.")

    def test_one_hard_day_too_many_reads_well(self) -> None:
        found = check_hard_days(
            week(hard(2)), context(limits=self.limits(IntensityLevel.NORMAL, max_hard_days=0))
        )

        assert (
            found[0].message == "The week has 1 hard day; your intensity settings allow at most 0."
        )

    def test_an_own_number_of_hard_days_counts(self) -> None:
        ctx = context(limits=self.limits(IntensityLevel.RELAXED, max_hard_days=4))

        assert check_hard_days(week(hard(0), hard(2), hard(4), hard(6)), ctx) == []

    @pytest.mark.parametrize(
        ("level", "warning", "error"),
        [
            (IntensityLevel.RELAXED, 115, 130),
            (IntensityLevel.NORMAL, 120, 140),
            (IntensityLevel.INTENSIVE, 130, 150),
        ],
    )
    def test_each_level_has_its_progression_limits(
        self, level: IntensityLevel, warning: int, error: int
    ) -> None:
        ctx = context(limits=LEVEL_LIMITS[level], recent_weeks=(100,))

        def codes(minutes: int) -> list[str]:
            return [f.code for f in check_progression(week(workout(1, minutes)), ctx)]

        assert codes(warning) == []
        assert codes(warning + 1) == ["volume_increase"]
        assert codes(error) == ["volume_increase"]
        assert codes(error + 1) == ["volume_jump"]

    def test_own_progression_limits_count(self) -> None:
        own = self.limits(
            IntensityLevel.NORMAL, progression_warning_percent=105, progression_error_percent=110
        )
        ctx = context(limits=own, typical_weekly_minutes=200)

        def codes(minutes: int) -> list[str]:
            return [f.code for f in check_progression(week(workout(1, minutes)), ctx)]

        assert codes(210) == []
        assert codes(211) == ["volume_increase"]
        assert codes(220) == ["volume_increase"]
        assert codes(221) == ["volume_jump"]


class TestHardDaysInARow:
    def test_a_hard_day_after_a_hard_day_is_a_warning_at_the_second(self) -> None:
        plan = week(hard(1), hard(2))

        assert check_hard_days_in_a_row(plan, context()) == [
            Finding(
                Severity.WARNING,
                "hard_days_in_a_row",
                "Wednesday is a hard day directly after another hard day.",
                "workouts[1]",
            )
        ]

    def test_a_day_between_them_is_enough(self) -> None:
        assert check_hard_days_in_a_row(week(hard(0), hard(2), hard(4)), context()) == []

    def test_three_in_a_row_give_two_warnings(self) -> None:
        found = check_hard_days_in_a_row(week(hard(3), hard(4), hard(5)), context())

        assert [f.path for f in found] == ["workouts[1]", "workouts[2]"]

    def test_the_end_of_the_week_and_its_start_are_not_in_a_row(self) -> None:
        # Sunday and the next Monday belong to different weeks: this plan cannot know the next one
        assert check_hard_days_in_a_row(week(hard(6), hard(0)), context()) == []

    def test_two_hard_workouts_on_one_day_are_not_in_a_row(self) -> None:
        assert check_hard_days_in_a_row(week(hard(2), hard(2)), context()) == []

    def test_a_hard_day_next_to_an_easy_day_is_fine(self) -> None:
        assert check_hard_days_in_a_row(week(hard(2), workout(3)), context()) == []

    def test_days_outside_the_week_do_not_count(self) -> None:
        assert check_hard_days_in_a_row(week(hard(-1), hard(0), hard(6), hard(7)), context()) == []

    def test_the_first_hard_workout_of_the_day_is_named(self) -> None:
        plan = week(hard(1), workout(2), hard(2), hard(2))

        found = check_hard_days_in_a_row(plan, context())

        assert [f.path for f in found] == ["workouts[2]"]

    def test_a_different_sport_on_the_next_day_still_counts(self) -> None:
        plan = week(hard(1), hard(2, sport=Sport.RUNNING))

        assert [f.code for f in check_hard_days_in_a_row(plan, context())] == ["hard_days_in_a_row"]


class TestAFreeDay:
    def test_a_workout_every_day_is_a_warning(self) -> None:
        plan = week(*(workout(d, 30) for d in range(7)))

        assert check_a_free_day(plan, context()) == [
            Finding(
                Severity.WARNING,
                "no_free_day",
                "Every day of the week has a workout; a day to rest is missing.",
                "workouts",
            )
        ]

    @pytest.mark.parametrize("missing", range(7))
    def test_one_free_day_is_enough(self, missing: int) -> None:
        plan = week(*(workout(d, 30) for d in range(7) if d != missing))

        assert check_a_free_day(plan, context()) == []

    def test_an_empty_week_has_free_days(self) -> None:
        assert check_a_free_day(week(), context()) == []

    def test_several_workouts_on_a_day_do_not_fill_the_others(self) -> None:
        plan = week(*(workout(d % 3) for d in range(14)))

        assert check_a_free_day(plan, context()) == []

    def test_workouts_outside_the_week_do_not_fill_a_day(self) -> None:
        plan = week(*(workout(d, 30) for d in range(6)), workout(7, 30))

        assert check_a_free_day(plan, context()) == []


class TestWorkoutsPerDay:
    def test_two_workouts_a_day_are_fine(self) -> None:
        assert (
            check_workouts_per_day(week(workout(1), workout(1, goal=Goal.TEMPO)), context()) == []
        )

    def test_a_third_workout_is_an_error_at_the_third(self) -> None:
        plan = week(workout(1, 30), workout(1, 40), workout(1, 50))

        assert check_workouts_per_day(plan, context()) == [
            Finding(
                Severity.ERROR,
                "many_workouts_in_a_day",
                "Tuesday has 3 workouts; at most 2 in a day are allowed.",
                "workouts[2]",
            )
        ]

    def test_a_double_day_does_not_make_a_third_workout_fine(self) -> None:
        plan = week(workout(1, 30), workout(1, 40), workout(1, 50))

        found = check_workouts_per_day(plan, context(double_days=(True,) * 7))

        assert [f.code for f in found] == ["many_workouts_in_a_day"]

    def test_a_day_is_named_once_however_many_workouts_it_has(self) -> None:
        plan = week(*(workout(1, 10 + n) for n in range(5)))

        found = check_workouts_per_day(plan, context())

        assert len(found) == 1
        assert found[0].message.startswith("Tuesday has 5 workouts")
        assert found[0].path == "workouts[2]"

    def test_each_busy_day_is_named_in_the_order_of_the_week(self) -> None:
        plan = week(
            *(workout(4, 10 + n) for n in range(3)), *(workout(1, 10 + n) for n in range(3))
        )

        assert [f.message[:8] for f in check_workouts_per_day(plan, context())] == [
            "Tuesday ",
            "Friday h",
        ]

    def test_the_third_is_found_by_its_place_in_the_list_not_by_its_day_position(self) -> None:
        plan = week(workout(1, 30), workout(2, 30), workout(1, 40), workout(1, 50))

        assert [f.path for f in check_workouts_per_day(plan, context())] == ["workouts[3]"]

    def test_workouts_outside_the_week_do_not_count(self) -> None:
        plan = week(workout(8, 30), workout(8, 31), workout(8, 32))

        assert check_workouts_per_day(plan, context()) == []


class TestDoubleDays:
    NO_DOUBLE_ON_TUESDAY = (True, False, True, True, True, True, True)

    def found(self, *workouts: Workout, **fields: Any) -> list[Finding]:
        return check_double_days(week(*workouts), context(**fields))

    def test_two_workouts_on_a_day_that_allows_them_are_fine(self) -> None:
        assert self.found(workout(1, 30), workout(1, 40)) == []

    def test_a_second_workout_on_another_day_is_an_error_at_the_second(self) -> None:
        found = self.found(workout(1, 30), workout(1, 40), double_days=self.NO_DOUBLE_ON_TUESDAY)

        assert found == [
            Finding(
                Severity.ERROR,
                "double_day_not_allowed",
                "Tuesday is not a day for two workouts; you did not allow a second one.",
                "workouts[1]",
            )
        ]

    def test_one_workout_on_such_a_day_is_fine(self) -> None:
        assert self.found(workout(1, 30), double_days=self.NO_DOUBLE_ON_TUESDAY) == []

    def test_the_other_days_are_not_affected(self) -> None:
        found = self.found(workout(2, 30), workout(2, 40), double_days=self.NO_DOUBLE_ON_TUESDAY)

        assert found == []

    def test_a_day_is_named_once_however_many_workouts_it_has(self) -> None:
        found = self.found(
            *(workout(1, 10 + n) for n in range(4)), double_days=self.NO_DOUBLE_ON_TUESDAY
        )

        assert [f.path for f in found] == ["workouts[1]"]

    def test_the_second_is_found_by_its_place_in_the_list(self) -> None:
        found = self.found(
            workout(1, 30),
            workout(2, 30),
            workout(1, 40),
            double_days=self.NO_DOUBLE_ON_TUESDAY,
        )

        assert [f.path for f in found] == ["workouts[2]"]

    def test_each_day_is_named_in_the_order_of_the_week(self) -> None:
        found = self.found(
            workout(4, 30),
            workout(4, 40),
            workout(1, 30),
            workout(1, 40),
            double_days=(True, False, True, True, False, True, True),
        )

        assert [f.message[:7] for f in found] == ["Tuesday", "Friday "]

    def test_workouts_outside_the_week_are_left_alone(self) -> None:
        assert self.found(workout(8, 30), workout(8, 40), double_days=(False,) * 7) == []

    def test_a_day_of_absence_still_follows_the_choice_of_its_weekday(self) -> None:
        found = self.found(
            workout(1, 30),
            workout(1, 40),
            double_days=self.NO_DOUBLE_ON_TUESDAY,
            absences=(None, "illness", None, None, None, None, None),
        )

        assert [f.code for f in found] == ["double_day_not_allowed"]

    def test_the_title_and_the_notes_are_not_repeated(self) -> None:
        found = self.found(
            workout(1, 30, title="SECRETMARKER", notes="SECRETMARKER"),
            workout(1, 40, title="SECRETMARKER"),
            double_days=self.NO_DOUBLE_ON_TUESDAY,
        )

        assert found
        assert "SECRETMARKER" not in repr(found)


class TestTheSameWorkoutTwice:
    def test_the_same_sport_goal_and_duration_on_one_day_is_a_warning_at_the_repeat(self) -> None:
        plan = week(workout(1, 60), workout(1, 60))

        assert check_duplicates(plan, context()) == [
            Finding(
                Severity.WARNING,
                "duplicate_workout",
                "Tuesday has the same workout twice (sport, goal and duration).",
                "workouts[1]",
            )
        ]

    def test_every_repeat_after_the_first_is_named(self) -> None:
        plan = week(workout(1, 60), workout(1, 60), workout(1, 60))

        assert [f.path for f in check_duplicates(plan, context())] == ["workouts[1]", "workouts[2]"]

    @pytest.mark.parametrize(
        "other",
        [
            {"minutes": 61},
            {"sport": Sport.RUNNING},
            {"goal": Goal.TEMPO},
        ],
    )
    def test_a_difference_in_sport_goal_or_duration_makes_it_a_different_workout(
        self, other: dict[str, Any]
    ) -> None:
        plan = week(workout(1, 60), workout(1, **{"minutes": 60, **other}))

        assert check_duplicates(plan, context()) == []

    def test_the_title_and_the_notes_do_not_matter(self) -> None:
        plan = week(workout(1, 60, title="A", notes="x"), workout(1, 60, title="B", notes="y"))

        assert len(check_duplicates(plan, context())) == 1

    def test_the_same_workout_on_two_days_is_normal(self) -> None:
        assert check_duplicates(week(workout(1, 60), workout(2, 60)), context()) == []

    def test_workouts_outside_the_week_are_left_alone(self) -> None:
        assert check_duplicates(week(workout(9, 60), workout(9, 60)), context()) == []

    def test_the_days_are_judged_in_the_order_of_the_week(self) -> None:
        plan = week(workout(4, 60), workout(1, 60), workout(4, 60), workout(1, 60))

        assert [f.message[:6] for f in check_duplicates(plan, context())] == ["Tuesda", "Friday"]


class TestProgression:
    def planned(self, minutes: int) -> WeekPlan:
        return week(workout(1, minutes))

    def test_without_a_reference_nothing_is_checked(self) -> None:
        assert check_progression(self.planned(1440), context(recent_weeks=())) == []

    def test_a_reference_of_no_minutes_is_no_reference(self) -> None:
        assert check_progression(self.planned(1440), context(recent_weeks=(0,))) == []
        assert check_progression(self.planned(1440), context(recent_weeks=(0, 0, 0))) == []

    def test_up_to_130_percent_is_fine(self) -> None:
        assert check_progression(self.planned(130), context(recent_weeks=(100,))) == []

    def test_a_minute_above_130_percent_is_a_warning(self) -> None:
        found = check_progression(self.planned(131), context(recent_weeks=(100,)))

        assert found == [
            Finding(
                Severity.WARNING,
                "volume_increase",
                "The week adds up to 131 minutes, 131 % of the average of 100 minutes "
                "of the last 1 week(s).",
                "workouts",
            )
        ]

    def test_exactly_150_percent_is_still_only_a_warning(self) -> None:
        found = check_progression(self.planned(150), context(recent_weeks=(100,)))

        assert [f.code for f in found] == ["volume_increase"]

    def test_a_minute_above_150_percent_is_an_error(self) -> None:
        found = check_progression(self.planned(151), context(recent_weeks=(100,)))

        assert found[0].severity is Severity.ERROR
        assert found[0].code == "volume_jump"
        assert found[0].path == "workouts"

    def test_the_reference_is_the_average_of_the_recent_weeks(self) -> None:
        weeks = (100, 200, 300)  # average 200: 130 % is 260, 150 % is 300

        assert check_progression(self.planned(260), context(recent_weeks=weeks)) == []
        assert [
            f.code for f in check_progression(self.planned(261), context(recent_weeks=weeks))
        ] == ["volume_increase"]
        assert [
            f.code for f in check_progression(self.planned(300), context(recent_weeks=weeks))
        ] == ["volume_increase"]
        assert [
            f.code for f in check_progression(self.planned(301), context(recent_weeks=weeks))
        ] == ["volume_jump"]

    def test_the_average_is_not_rounded_before_comparing(self) -> None:
        # (100 + 101) / 2 = 100.5 minutes: 130 % is 130.65, so 130 passes and 131 does not
        weeks = (100, 101)

        assert check_progression(self.planned(130), context(recent_weeks=weeks)) == []
        assert check_progression(self.planned(131), context(recent_weeks=weeks)) != []

    def test_a_smaller_week_is_fine(self) -> None:
        assert check_progression(self.planned(10), context(recent_weeks=(500,))) == []
        assert check_progression(week(), context(recent_weeks=(500,))) == []

    def test_only_the_workouts_of_the_week_count(self) -> None:
        plan = week(workout(1, 100), workout(9, 5000), workout(-2, 5000))

        assert check_progression(plan, context(recent_weeks=(100,))) == []

    def test_all_workouts_of_the_week_are_added_up(self) -> None:
        plan = week(workout(1, 50), workout(2, 50), workout(3, 51))

        assert check_progression(plan, context(recent_weeks=(100,))) != []

    def test_the_message_names_the_average_and_the_number_of_weeks(self) -> None:
        found = check_progression(self.planned(400), context(recent_weeks=(100, 200, 300, 200)))

        assert found[0].message == (
            "The week adds up to 400 minutes, 200 % of the average of 200 minutes "
            "of the last 4 week(s)."
        )


class TestTheTypicalWeek:
    """The athlete's own word about a normal week: the reference when it is higher than the recent
    weeks (a break must not keep a returning athlete at the few weeks since)."""

    def planned(self, minutes: int) -> WeekPlan:
        return week(workout(1, minutes))

    def codes(self, minutes: int, **fields: Any) -> list[str]:
        return [f.code for f in check_progression(self.planned(minutes), context(**fields))]

    def test_it_is_a_reference_of_its_own_when_there_are_no_recent_weeks(self) -> None:
        assert self.codes(130, typical_weekly_minutes=100) == []
        assert self.codes(131, typical_weekly_minutes=100) == ["volume_increase"]
        assert self.codes(150, typical_weekly_minutes=100) == ["volume_increase"]
        assert self.codes(151, typical_weekly_minutes=100) == ["volume_jump"]

    def test_the_higher_one_counts_after_a_break(self) -> None:
        # recent 108 alone: 140 is the limit. With a typical week of 360 the limits are 468 and 540.
        assert self.codes(141, recent_weeks=(108,)) == ["volume_increase"]
        assert self.codes(468, recent_weeks=(108,), typical_weekly_minutes=360) == []
        assert self.codes(469, recent_weeks=(108,), typical_weekly_minutes=360) == [
            "volume_increase"
        ]
        assert self.codes(540, recent_weeks=(108,), typical_weekly_minutes=360) == [
            "volume_increase"
        ]
        assert self.codes(541, recent_weeks=(108,), typical_weekly_minutes=360) == ["volume_jump"]

    def test_a_typical_week_below_the_recent_weeks_changes_nothing(self) -> None:
        weeks = (200, 200)

        for minutes in (260, 261, 300, 301):
            assert self.codes(minutes, recent_weeks=weeks, typical_weekly_minutes=50) == self.codes(
                minutes, recent_weeks=weeks
            )

    def test_the_recent_weeks_name_themselves_when_both_are_equal(self) -> None:
        found = check_progression(
            self.planned(400), context(recent_weeks=(200,), typical_weekly_minutes=200)
        )

        assert "the average of 200 minutes of the last 1 week(s)" in found[0].message
        assert "typical" not in found[0].message

    def test_no_typical_week_or_one_of_no_minutes_is_no_reference(self) -> None:
        assert self.codes(1440, typical_weekly_minutes=None) == []
        assert self.codes(1440, typical_weekly_minutes=0) == []
        assert self.codes(1440, recent_weeks=(0,), typical_weekly_minutes=0) == []
        assert self.codes(141, recent_weeks=(108,), typical_weekly_minutes=0) == ["volume_increase"]

    def test_the_message_names_the_typical_week_when_it_is_the_reference(self) -> None:
        found = check_progression(
            self.planned(469), context(recent_weeks=(108,), typical_weekly_minutes=360)
        )

        assert found == [
            Finding(
                Severity.WARNING,
                "volume_increase",
                "The week adds up to 469 minutes, 130 % of your typical week of 360 minutes.",
                "workouts",
            )
        ]

    def test_a_week_below_the_typical_week_is_fine(self) -> None:
        assert self.codes(30, recent_weeks=(108,), typical_weekly_minutes=360) == []
        assert check_progression(week(), context(typical_weekly_minutes=360)) == []

    def test_only_the_workouts_of_the_week_count(self) -> None:
        plan = week(workout(1, 100), workout(9, 5000), workout(-2, 5000))

        assert check_progression(plan, context(typical_weekly_minutes=100)) == []

    def test_the_share_of_the_typical_week_that_counts_is_a_constant(self) -> None:
        assert rules.TYPICAL_VOLUME_PERCENT == 100

    def test_a_lower_share_makes_the_reference_smaller_and_says_so(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(rules, "TYPICAL_VOLUME_PERCENT", 70)

        # 70 % of 101 is 70.7 minutes, not rounded: 130 % of it is 91.91
        assert self.codes(91, typical_weekly_minutes=101) == []
        found = check_progression(self.planned(92), context(typical_weekly_minutes=101))
        assert [f.code for f in found] == ["volume_increase"]
        assert found[0].message == (
            "The week adds up to 92 minutes, 130 % of 70 % of your typical week of 101 minutes."
        )

    def test_a_lower_share_still_loses_to_higher_recent_weeks(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(rules, "TYPICAL_VOLUME_PERCENT", 70)

        # 70 % of 360 is 252; the recent average of 300 is higher
        found = check_progression(
            self.planned(400), context(recent_weeks=(300,), typical_weekly_minutes=360)
        )

        assert "the average of 300 minutes" in found[0].message


class TestTheEasyShare:
    """At least the level's share of the endurance minutes is easy (normal: 80 %)."""

    def found(self, *workouts: Workout, **fields: Any) -> list[Finding]:
        return check_easy_share(week(*workouts), context(**fields))

    @staticmethod
    def intervals(offset: int, minutes: int, **fields: Any) -> Workout:
        # 10 warm-up, 4 x (5 work in zone 5 + 3 recovery without a zone), 18 cool-down: 60 minutes
        segments = (
            Segment(SegmentKind.WARMUP, 600, 1, ZoneSystem.POWER, 1),
            Segment(SegmentKind.WORK, 300, 4, ZoneSystem.POWER, 5),
            Segment(SegmentKind.RECOVERY, 180, 4),
            Segment(SegmentKind.COOLDOWN, 1080, 1),
        )
        return workout(offset, minutes, goal=Goal.VO2MAX, segments=segments, **fields)

    def test_too_little_easy_is_a_warning_with_the_share_rounded_down(self) -> None:
        # 240 easy of 301: 79.7 %
        found = self.found(workout(0, 240), hard(2, 61), limits=LEVEL_LIMITS[IntensityLevel.NORMAL])

        assert found == [
            Finding(
                Severity.WARNING,
                "easy_share_low",
                "79 % of the endurance minutes are easy; your intensity settings ask for at "
                "least 80 %.",
                "workouts",
            )
        ]

    def test_exactly_the_share_passes(self) -> None:
        assert (
            self.found(workout(0, 240), hard(2, 60), limits=LEVEL_LIMITS[IntensityLevel.NORMAL])
            == []
        )

    @pytest.mark.parametrize(
        ("level", "easy_minutes_needed"),
        [(IntensityLevel.RELAXED, 85), (IntensityLevel.NORMAL, 80), (IntensityLevel.INTENSIVE, 75)],
    )
    def test_each_level_asks_for_its_share(
        self, level: IntensityLevel, easy_minutes_needed: int
    ) -> None:
        ctx = {"limits": LEVEL_LIMITS[level]}
        hard_minutes = 100 - easy_minutes_needed

        assert self.found(workout(0, easy_minutes_needed), hard(2, hard_minutes), **ctx) == []
        assert self.found(workout(0, easy_minutes_needed - 1), hard(2, hard_minutes + 1), **ctx)

    def test_moderate_is_not_easy(self) -> None:
        tempo = workout(2, 50, zone_system=ZoneSystem.POWER, zone=3)

        assert [f.code for f in self.found(workout(0, 50), tempo)] == ["easy_share_low"]

    def test_strength_counts_neither_way(self) -> None:
        strength = workout(1, 300, sport=Sport.STRENGTH, goal=Goal.STRENGTH)

        assert self.found(workout(0, 80), hard(2, 20), strength) == self.found(
            workout(0, 80), hard(2, 20)
        )
        assert self.found(workout(0, 75), hard(2, 25), strength) == self.found(
            workout(0, 75), hard(2, 25)
        )

    def test_a_week_without_endurance_minutes_is_not_checked(self) -> None:
        assert self.found() == []
        assert self.found(workout(1, 60, sport=Sport.STRENGTH, goal=Goal.STRENGTH)) == []

    def test_running_and_swimming_count_like_cycling(self) -> None:
        for sport in (Sport.RUNNING, Sport.SWIMMING):
            assert self.found(workout(0, 50), hard(2, 50, sport=sport)) != []

    def test_workouts_outside_the_week_do_not_count(self) -> None:
        assert self.found(workout(1, 100), hard(8, 500), hard(-1, 500)) == []

    def test_an_own_share_counts(self) -> None:
        own = dataclasses.replace(INTENSIVE, easy_share_percent=50)

        assert self.found(workout(0, 50), hard(2, 50), limits=own) == []

    def test_segments_count_one_by_one(self) -> None:
        # warm-up 10 (zone 1), recovery 12 (no zone), cool-down 18 (no zone): 40 of 60 easy
        assert easy_minutes(self.intervals(0, 60)) == 40

    def test_the_segments_share_is_applied_to_the_duration(self) -> None:
        # the segments may differ from the duration by a minute; the share is what counts
        assert easy_minutes(self.intervals(0, 61)) == Fraction(40 * 61, 60)

    def test_a_segment_without_a_zone_is_as_easy_as_the_workout(self) -> None:
        steady = (Segment(SegmentKind.STEADY, 3600),)

        assert easy_minutes(workout(0, 60, segments=steady)) == 60
        assert easy_minutes(workout(0, 60, goal=Goal.THRESHOLD, segments=steady)) == 0
        assert (
            easy_minutes(workout(0, 60, zone_system=ZoneSystem.POWER, zone=3, segments=steady)) == 0
        )

    def test_the_zone_of_a_segment_wins_over_the_workout(self) -> None:
        easy_steady = (Segment(SegmentKind.STEADY, 3600, 1, ZoneSystem.POWER, 2),)
        hard_warmup = (Segment(SegmentKind.WARMUP, 3600, 1, ZoneSystem.POWER, 4),)

        assert easy_minutes(workout(0, 60, goal=Goal.THRESHOLD, segments=easy_steady)) == 60
        assert easy_minutes(workout(0, 60, segments=hard_warmup)) == 0

    def test_without_segments_a_workout_counts_by_its_intensity(self) -> None:
        assert easy_minutes(workout(0, 60)) == 60
        assert easy_minutes(workout(0, 60, zone_system=ZoneSystem.POWER, zone=2)) == 60
        assert easy_minutes(workout(0, 60, zone_system=ZoneSystem.POWER, zone=3)) == 0
        assert easy_minutes(hard(0, 60)) == 0

    def test_a_typical_interval_week_passes_on_normal(self) -> None:
        # two interval sessions and three easy rides: 80 easy of 120 + 3 x 120 = 440 of 480
        plan = (self.intervals(1, 60), self.intervals(3, 60), *(workout(d, 120) for d in (0, 5, 6)))

        assert self.found(*plan, limits=LEVEL_LIMITS[IntensityLevel.NORMAL]) == []


class TestTheTimesOfDay:
    M, A, E = Slot.MORNING, Slot.AFTERNOON, Slot.EVENING

    def found(self, *workouts: Workout) -> list[Finding]:
        return check_times_of_day(week(*workouts), context())

    def test_a_single_workout_needs_no_time_of_day(self) -> None:
        assert self.found(workout(1, 30)) == []
        assert self.found(workout(1, 30, slot=self.E)) == []

    def test_two_workouts_at_different_times_are_fine(self) -> None:
        assert self.found(workout(1, 30, slot=self.M), workout(1, 30, slot=self.E)) == []
        assert self.found(workout(1, 30, slot=self.E), workout(1, 30, slot=self.A)) == []

    def test_three_workouts_at_three_times_are_fine(self) -> None:
        plan = (
            workout(1, 30, slot=self.M),
            workout(1, 30, slot=self.A),
            workout(1, 30, slot=self.E),
        )

        assert self.found(*plan) == []

    @pytest.mark.parametrize("slot", list(Slot))
    def test_two_workouts_at_the_same_time_are_an_error_at_the_second(self, slot: Slot) -> None:
        found = self.found(workout(2, 30, slot=slot), workout(2, 30, slot=slot))

        assert found == [
            Finding(
                Severity.ERROR,
                "same_slot",
                f"Wednesday has two workouts in the {slot.value}.",
                "workouts[1].slot",
            )
        ]

    def test_every_repeat_is_named(self) -> None:
        found = self.found(
            workout(2, 30, slot=self.M), workout(2, 30, slot=self.M), workout(2, 30, slot=self.M)
        )

        assert [f.path for f in found] == ["workouts[1].slot", "workouts[2].slot"]

    def test_the_same_time_on_different_days_is_fine(self) -> None:
        assert self.found(workout(1, 30, slot=self.M), workout(2, 30, slot=self.M)) == []

    def test_several_workouts_without_a_time_are_one_warning_at_the_first(self) -> None:
        found = self.found(workout(3, 30), workout(3, 30, sport=Sport.RUNNING))

        assert found == [
            Finding(
                Severity.WARNING,
                "slot_missing",
                "Thursday has 2 workouts; say for each when it is (morning, afternoon or evening).",
                "workouts[0].slot",
            )
        ]

    def test_one_without_a_time_among_two_is_named_at_that_one(self) -> None:
        found = self.found(workout(3, 30, slot=self.M), workout(3, 30, sport=Sport.RUNNING))

        assert [(f.code, f.path) for f in found] == [("slot_missing", "workouts[1].slot")]

    def test_it_is_named_once_a_day_however_many_lack_a_time(self) -> None:
        found = self.found(
            workout(3, 30), workout(3, 30, sport=Sport.RUNNING), workout(3, 30, slot=self.E)
        )

        assert len(found) == 1
        assert found[0].message.startswith("Thursday has 3 workouts")

    def test_two_days_are_named_each_for_itself(self) -> None:
        found = self.found(
            workout(1, 30), workout(1, 30, sport=Sport.RUNNING), workout(4, 30), workout(4, 30)
        )

        assert [f.path for f in found] == ["workouts[0].slot", "workouts[2].slot"]

    def test_a_repeat_and_a_missing_time_on_one_day_are_both_named(self) -> None:
        found = self.found(workout(1, 30, slot=self.M), workout(1, 30, slot=self.M), workout(1, 30))

        assert [(f.code, f.severity) for f in found] == [
            ("same_slot", Severity.ERROR),
            ("slot_missing", Severity.WARNING),
        ]

    def test_workouts_without_a_time_are_never_the_same_time(self) -> None:
        found = self.found(workout(1, 30), workout(1, 30, sport=Sport.RUNNING))

        assert [f.code for f in found] == ["slot_missing"]

    def test_workouts_outside_the_week_are_left_to_their_own_rule(self) -> None:
        assert self.found(workout(9, 30), workout(9, 30)) == []

    def test_nothing_the_coach_wrote_is_repeated(self) -> None:
        found = self.found(
            workout(1, 30, slot=self.M, title="SECRETMARKER", notes="SECRETMARKER"),
            workout(1, 30, slot=self.M, title="SECRETMARKER"),
            workout(1, 30, title="SECRETMARKER"),
        )

        assert found
        assert "SECRETMARKER" not in repr(found)


class TestTheLists:
    def test_the_rhythm_checks_come_after_the_basic_ones(self) -> None:
        assert ALL_CHECKS == BASIC_CHECKS + RHYTHM_CHECKS
        assert RHYTHM_CHECKS == (
            check_hard_days,
            check_hard_days_in_a_row,
            check_a_free_day,
            check_workouts_per_day,
            check_double_days,
            check_duplicates,
            check_progression,
            check_easy_share,
            check_times_of_day,
        )

    def test_which_rules_are_errors_and_which_warnings(self) -> None:
        plan = week(
            *(hard(d, 30) for d in range(7)), workout(0, 30), workout(0, 30), workout(0, 30)
        )
        ctx = context(recent_weeks=(10,))

        found = [f for check in RHYTHM_CHECKS for f in check(plan, ctx)]
        severities = {f.code: f.severity for f in found}

        assert severities == {
            "too_many_hard_days": Severity.ERROR,
            "hard_days_in_a_row": Severity.WARNING,
            "no_free_day": Severity.WARNING,
            "many_workouts_in_a_day": Severity.ERROR,
            "duplicate_workout": Severity.WARNING,
            "volume_jump": Severity.ERROR,
            "easy_share_low": Severity.WARNING,
            "slot_missing": Severity.WARNING,
        }

    def test_a_context_for_another_week_is_a_programming_error(self) -> None:
        for check in RHYTHM_CHECKS:
            with pytest.raises(ValueError, match="another week"):
                check(week(), context(week_start=day(7)))


class TestNothingTheCoachWroteIsRepeated:
    MARKER = "SECRET-TITLE-MARKER"

    def test_no_message_holds_a_title_or_a_note(self) -> None:
        plan = week(
            *(hard(d, 500, title=self.MARKER, notes=self.MARKER) for d in range(7)),
            hard(0, 500, title=self.MARKER),
            hard(0, 500, title=self.MARKER),
        )

        found = [f for check in RHYTHM_CHECKS for f in check(plan, context(recent_weeks=(10,)))]

        assert len(found) >= 5
        assert all(self.MARKER not in f.message and self.MARKER not in f.path for f in found)


class TestWhateverIsPlanned:
    def test_no_rhythm_check_raises_and_the_findings_are_well_formed(self) -> None:
        rng = random.Random(20261114)
        total = 0
        for _ in range(1500):
            workouts = []
            for _ in range(rng.randint(0, 12)):
                system = rng.choice([None, *ZoneSystem])
                workouts.append(
                    Workout(
                        day=day(rng.randint(-3, 10)),
                        sport=rng.choice(list(Sport)),
                        title="t",
                        goal=rng.choice(list(Goal)),
                        duration_minutes=rng.randint(1, 1440),
                        zone_system=system,
                        zone=None if system is None else rng.randint(1, 5),
                    )
                )
            plan = week(*workouts)
            ctx = context(
                recent_weeks=tuple(rng.randint(0, 3000) for _ in range(rng.randint(0, 4))),
                typical_weekly_minutes=rng.choice([None, 0, rng.randint(1, 5000)]),
            )

            found = [f for check in RHYTHM_CHECKS for f in check(plan, ctx)]
            total += len(found)

            assert found == [f for check in RHYTHM_CHECKS for f in check(plan, ctx)]
            for finding in found:
                assert finding.code and finding.message and finding.path.startswith("workouts")
                assert isinstance(finding.severity, Severity)
        assert total > 1000

    def test_the_module_still_lists_every_check_it_defines(self) -> None:
        defined = {name for name in vars(rules) if name.startswith("check_")}

        assert defined == {c.__name__ for c in ALL_CHECKS}
