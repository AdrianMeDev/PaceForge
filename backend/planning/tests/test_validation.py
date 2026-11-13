import dataclasses
from datetime import date, timedelta
from typing import Any

import pytest

from planning.context import PlanContext
from planning.rules import ALL_CHECKS, Finding, Severity
from planning.schema import Goal, Segment, SegmentKind, Sport, WeekPlan, Workout, ZoneSystem
from planning.validation import Report, validate_week

MONDAY = date(2027, 7, 12)
SYSTEMS = frozenset(
    {
        (Sport.CYCLING, ZoneSystem.POWER),
        (Sport.RUNNING, ZoneSystem.PACE),
        (Sport.RUNNING, ZoneSystem.HEART_RATE),
    }
)


def workout(offset: int, minutes: int, **fields: Any) -> Workout:
    data: dict[str, Any] = {
        "day": MONDAY + timedelta(days=offset),
        "sport": Sport.CYCLING,
        "title": "Ride",
        "goal": Goal.ENDURANCE,
        "duration_minutes": minutes,
        **fields,
    }
    return Workout(**data)


def context(**fields: Any) -> PlanContext:
    data: dict[str, Any] = {
        "week_start": MONDAY,
        "minutes": (90, 0, 90, 0, 120, 120, 0),
        "absences": (None,) * 7,
        "weekly_budget": None,
        "weekly_minutes": 420,
        "zone_systems": SYSTEMS,
        "recent_weeks": (300, 360, 330),
        **fields,
    }
    return PlanContext(**data)


def good_week() -> WeekPlan:
    return WeekPlan(
        MONDAY,
        (
            workout(
                0,
                90,
                zone_system=ZoneSystem.POWER,
                zone=2,
                segments=(Segment(SegmentKind.STEADY, 5400, 1, ZoneSystem.POWER, 2),),
            ),
            workout(2, 60, sport=Sport.RUNNING, zone_system=ZoneSystem.PACE, zone=3),
            workout(
                4,
                100,
                sport=Sport.RUNNING,
                goal=Goal.THRESHOLD,
                segments=(
                    Segment(SegmentKind.WARMUP, 1200, 1, ZoneSystem.PACE, 1),
                    Segment(SegmentKind.WORK, 600, 4, ZoneSystem.PACE, 4),
                    Segment(SegmentKind.RECOVERY, 300, 4, ZoneSystem.PACE, 1),
                    Segment(SegmentKind.COOLDOWN, 1200, 1, ZoneSystem.PACE, 1),
                ),
            ),
            workout(5, 90, sport=Sport.CYCLING, zone_system=ZoneSystem.POWER, zone=2),
        ),
    )


class TestTheReport:
    def test_a_good_week_is_valid_without_any_finding(self) -> None:
        report = validate_week(good_week(), context())

        assert report == Report(())
        assert report.valid
        assert (report.errors, report.warnings) == ((), ())

    def test_an_empty_week_is_valid(self) -> None:
        assert validate_week(WeekPlan(MONDAY), context()).valid

    def test_one_error_makes_the_plan_invalid(self) -> None:
        plan = dataclasses.replace(
            good_week(), workouts=(workout(1, 60),)
        )  # Tuesday offers nothing

        report = validate_week(plan, context())

        assert not report.valid
        assert [f.code for f in report.errors] == ["day_over_capacity"]

    def test_warnings_alone_do_not_make_it_invalid(self) -> None:
        # two hard days in a row: a warning only
        plan = WeekPlan(
            MONDAY,
            (workout(4, 60, goal=Goal.THRESHOLD), workout(5, 60, goal=Goal.VO2MAX)),
        )

        report = validate_week(plan, context())

        assert report.valid
        assert [f.code for f in report.warnings] == ["hard_days_in_a_row"]
        assert report.errors == ()

    def test_errors_and_warnings_are_told_apart(self) -> None:
        plan = WeekPlan(
            MONDAY,
            (
                workout(1, 60, goal=Goal.THRESHOLD),
                workout(2, 60, goal=Goal.THRESHOLD),
            ),
        )

        report = validate_week(plan, context(minutes=(0, 0, 0, 0, 0, 0, 0), weekly_minutes=0))

        assert {f.severity for f in report.findings} == {Severity.ERROR, Severity.WARNING}
        assert all(f.severity is Severity.ERROR for f in report.errors)
        assert all(f.severity is Severity.WARNING for f in report.warnings)
        assert len(report.errors) + len(report.warnings) == len(report.findings)

    def test_the_report_cannot_be_changed(self) -> None:
        report = validate_week(good_week(), context())

        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(report, "findings", ())  # noqa: B010
        assert isinstance(report.findings, tuple)


class TestTheOrder:
    def test_structure_comes_before_rhythm_and_each_check_keeps_its_place(self) -> None:
        plan = WeekPlan(
            MONDAY,
            (
                workout(9, 60),  # outside the week
                workout(4, 10, goal=Goal.THRESHOLD),
                workout(4, 10, goal=Goal.THRESHOLD),  # twice the same on a day
                workout(5, 10, goal=Goal.THRESHOLD),  # hard in a row
            ),
        )

        report = validate_week(plan, context())

        assert [f.code for f in report.findings] == [
            "outside_week",
            "hard_days_in_a_row",
            "duplicate_workout",
        ]

    def test_the_findings_follow_the_list_of_checks(self) -> None:
        plan = good_week()
        ctx = context()

        expected = tuple(f for check in ALL_CHECKS for f in check(plan, ctx))

        assert validate_week(plan, ctx).findings == expected

    def test_the_same_input_gives_the_same_report(self) -> None:
        plan = WeekPlan(MONDAY, (workout(9, 60), workout(1, 999, goal=Goal.THRESHOLD)))
        ctx = context()

        assert validate_week(plan, ctx) == validate_week(plan, ctx)


class TestEveryReasonAtOnce:
    def test_a_bad_week_collects_the_findings_of_every_rule(self) -> None:
        plan = WeekPlan(
            MONDAY,
            (
                workout(9, 60),
                workout(1, 90, segments=(Segment(SegmentKind.WORK, 60),)),
                workout(2, 60, sport=Sport.SWIMMING, zone_system=ZoneSystem.POWER, zone=2),
                *(workout(d, 400, goal=Goal.THRESHOLD) for d in (3, 4, 5, 6)),
            ),
        )

        report = validate_week(plan, context(recent_weeks=(100,)))

        assert not report.valid
        codes = {f.code for f in report.findings}
        assert {
            "outside_week",
            "segments_mismatch",
            "zone_system_not_for_sport",
            "day_over_capacity",
            "week_over_capacity",
            "too_many_hard_days",
            "hard_days_in_a_row",
            "volume_jump",
        } <= codes

    def test_the_finding_type_is_the_one_of_the_rules(self) -> None:
        report = validate_week(WeekPlan(MONDAY, (workout(9, 60),)), context())

        assert all(isinstance(f, Finding) for f in report.findings)
