from dataclasses import replace
from datetime import date
from typing import Any

import pytest

from activities.models import Activity
from planning.context import PlanContext
from planning.load import DEFAULT_STRENGTH_RPE, estimate_workout_load, week_load
from planning.rules import check_day_capacity, check_week_capacity
from planning.schema import (
    Exercise,
    ExerciseEquipment,
    ExerciseRegion,
    Goal,
    Segment,
    SegmentKind,
    Sport,
    WeekPlan,
    Workout,
    ZoneSystem,
    to_json,
)

MONDAY = date(2027, 7, 19)


def workout(**fields: Any) -> Workout:
    return replace(Workout(MONDAY, Sport.RUNNING, "Run", Goal.ENDURANCE, 60), **fields)


def exercise(rpe: int | None, sets: int = 3) -> Exercise:
    return Exercise(
        "Squat", ExerciseRegion.LEGS, ExerciseEquipment.BODYWEIGHT, sets, reps=10, rpe=rpe
    )


class TestEndurance:
    @pytest.mark.parametrize(
        ("system", "rates"),
        [
            (ZoneSystem.HEART_RATE, (35, 55, 75, 100, 120)),
            (ZoneSystem.PACE, (35, 55, 75, 100, 120)),
            (ZoneSystem.POWER, (30, 50, 70, 95, 115, 130, 145)),
        ],
    )
    def test_every_zone_has_its_hourly_rate(
        self, system: ZoneSystem, rates: tuple[int, ...]
    ) -> None:
        for zone, rate in enumerate(rates, start=1):
            item = workout(zone_system=system, zone=zone)
            assert estimate_workout_load(item) == rate
            assert estimate_workout_load(replace(item, duration_minutes=120)) == rate * 2

    @pytest.mark.parametrize(
        ("goal", "rate"),
        [
            (Goal.RECOVERY, 35),
            (Goal.ENDURANCE, 55),
            (Goal.TEMPO, 75),
            (Goal.THRESHOLD, 95),
            (Goal.VO2MAX, 115),
            (Goal.OTHER, 55),
        ],
    )
    @pytest.mark.parametrize("sport", [Sport.RUNNING, Sport.CYCLING, Sport.SWIMMING])
    def test_an_unzoned_session_uses_its_goal(self, goal: Goal, rate: int, sport: Sport) -> None:
        assert estimate_workout_load(workout(sport=sport, goal=goal)) == rate

    @pytest.mark.parametrize("minutes", [30, 60, 90])
    def test_segments_use_repeats_and_scale_to_the_declared_minutes(self, minutes: int) -> None:
        item = workout(
            duration_minutes=minutes,
            zone_system=ZoneSystem.POWER,
            zone=7,
            segments=(
                Segment(SegmentKind.WARMUP, 600, 1, ZoneSystem.POWER, 1),
                Segment(SegmentKind.WORK, 300, 4, ZoneSystem.POWER, 4),
            ),
        )
        # (600 * 30 + 1200 * 95) / 1800 = 73 1/3 points per hour.
        assert estimate_workout_load(item) == {30: 37, 60: 73, 90: 110}[minutes]

    def test_an_unzoned_segment_uses_the_workout_zone_then_the_goal(self) -> None:
        item = workout(
            zone_system=ZoneSystem.POWER,
            zone=2,
            goal=Goal.THRESHOLD,
            segments=(
                Segment(SegmentKind.WORK, 600, 1, ZoneSystem.POWER, 4),
                Segment(SegmentKind.RECOVERY, 600),
            ),
        )
        assert estimate_workout_load(item) == 73  # mean of 95 and 50
        assert estimate_workout_load(replace(item, zone_system=None, zone=None)) == 95

    def test_rounding_happens_once_half_up(self) -> None:
        assert estimate_workout_load(workout(duration_minutes=6)) == 6  # 5.5
        item = workout(
            duration_minutes=1,
            segments=(
                Segment(SegmentKind.WARMUP, 30, 1, ZoneSystem.PACE, 1),
                Segment(SegmentKind.WORK, 30, 1, ZoneSystem.PACE, 2),
            ),
        )
        assert estimate_workout_load(item) == 1  # 0.75, not rounded per segment

    def test_stretching_is_not_training_load(self) -> None:
        assert estimate_workout_load(workout(stretching_minutes=60)) == 55


class TestStrength:
    def test_the_mean_of_specified_exercise_rpes_sets_the_rate(self) -> None:
        item = workout(
            sport=Sport.STRENGTH,
            goal=Goal.STRENGTH,
            duration_minutes=45,
            exercises=(exercise(4, sets=10), exercise(9, sets=1), exercise(None)),
        )
        assert estimate_workout_load(item) == 49  # 45 / 60 * 6.5 * 10 = 48.75

    @pytest.mark.parametrize("exercises", [(), (exercise(None), exercise(None))])
    def test_no_exercise_rpe_uses_the_default(self, exercises: tuple[Exercise, ...]) -> None:
        assert DEFAULT_STRENGTH_RPE == 6
        assert estimate_workout_load(workout(sport=Sport.STRENGTH, exercises=exercises)) == 60

    def test_half_points_round_up_exactly(self) -> None:
        item = workout(sport=Sport.STRENGTH, duration_minutes=21, exercises=(exercise(3),))
        assert estimate_workout_load(item) == 11  # 10.5


class TestWeekTotals:
    def test_sports_and_total_include_unplanned_and_unrated_activities(self) -> None:
        plan = WeekPlan(
            MONDAY,
            (workout(duration_minutes=30), workout(sport=Sport.STRENGTH)),
        )
        activities = [
            Activity(sport="running", timer_seconds=1800, elapsed_seconds=3600, rpe=5),
            Activity(sport="running", elapsed_seconds=30),
            Activity(sport="running", timer_seconds=0, elapsed_seconds=600, rpe=10),
            Activity(sport="cycling", elapsed_seconds=3600, rpe=10, training_load=74.5),
            Activity(sport="other", training_load=10),
            Activity(sport="swimming"),
        ]

        assert week_load(plan, activities) == {
            "sports": [
                {
                    "sport": "running",
                    "planned_minutes": 30,
                    "done_minutes": 31,
                    "planned_load": 28,
                    "done_load": 25,
                },
                {
                    "sport": "cycling",
                    "planned_minutes": 0,
                    "done_minutes": 60,
                    "planned_load": 0,
                    "done_load": 75,
                },
                {
                    "sport": "swimming",
                    "planned_minutes": 0,
                    "done_minutes": 0,
                    "planned_load": 0,
                    "done_load": 0,
                },
                {
                    "sport": "strength",
                    "planned_minutes": 60,
                    "done_minutes": 0,
                    "planned_load": 60,
                    "done_load": 0,
                },
                {
                    "sport": "other",
                    "planned_minutes": 0,
                    "done_minutes": 0,
                    "planned_load": 0,
                    "done_load": 10,
                },
            ],
            "total": {
                "planned_minutes": 90,
                "done_minutes": 91,
                "planned_load": 88,
                "done_load": 110,
            },
        }

    def test_an_empty_week_has_zero_totals(self) -> None:
        assert week_load(WeekPlan(MONDAY), []) == {
            "sports": [],
            "total": {"planned_minutes": 0, "done_minutes": 0, "planned_load": 0, "done_load": 0},
        }

    def test_seconds_are_added_before_rounding_and_total_adds_sport_minutes(self) -> None:
        activities = [
            Activity(sport="running", timer_seconds=15),
            Activity(sport="running", timer_seconds=15),
            Activity(sport="cycling", timer_seconds=30),
        ]
        assert week_load(WeekPlan(MONDAY), activities)["total"]["done_minutes"] == 2


class TestMinutesStayAuthoritative:
    @pytest.mark.parametrize("zone", [1, 7])
    @pytest.mark.parametrize("minutes", [60, 61])
    def test_capacity_uses_duration_even_when_load_is_lower_or_higher(
        self, zone: int, minutes: int
    ) -> None:
        plan = WeekPlan(
            MONDAY, (workout(duration_minutes=minutes, zone_system=ZoneSystem.POWER, zone=zone),)
        )
        context = PlanContext(MONDAY, (60,) * 7, (None,) * 7, 60, 60, frozenset(), ())
        before = to_json(plan)
        week_load(plan, [])
        assert to_json(plan) == before
        assert "estimated_load" not in before["workouts"][0]
        assert [f.code for f in check_day_capacity(plan, context)] == (
            ["day_over_capacity"] if minutes > 60 else []
        )
        assert [f.code for f in check_week_capacity(plan, context)] == (
            ["week_over_capacity"] if minutes > 60 else []
        )
