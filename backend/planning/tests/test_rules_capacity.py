import ast
import random
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest

from planning import rules
from planning.context import PlanContext
from planning.rules import (
    BASIC_CHECKS,
    DURATION_TOLERANCE_SECONDS,
    SPORT_ZONE_SYSTEMS,
    Finding,
    Severity,
    basic_checks,
    check_day_capacity,
    check_inside_week,
    check_segments_add_up,
    check_week_capacity,
    check_zone_systems,
)
from planning.schema import Goal, Segment, SegmentKind, Sport, WeekPlan, Workout, ZoneSystem

MONDAY = date(2027, 7, 12)
assert MONDAY.weekday() == 0
ALL_SYSTEMS = frozenset(
    {
        (Sport.CYCLING, ZoneSystem.POWER),
        (Sport.CYCLING, ZoneSystem.HEART_RATE),
        (Sport.RUNNING, ZoneSystem.PACE),
        (Sport.RUNNING, ZoneSystem.HEART_RATE),
    }
)


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


def week(*workouts: Workout) -> WeekPlan:
    return WeekPlan(MONDAY, tuple(workouts))


def context(**fields: Any) -> PlanContext:
    data: dict[str, Any] = {
        "week_start": MONDAY,
        "minutes": (120,) * 7,
        "absences": (None,) * 7,
        "weekly_budget": None,
        "weekly_minutes": 840,
        "zone_systems": ALL_SYSTEMS,
        "recent_weeks": (),
        **fields,
    }
    return PlanContext(**data)


def codes(findings: list[Finding]) -> list[str]:
    return [finding.code for finding in findings]


class TestInsideTheWeek:
    @pytest.mark.parametrize("offset", range(7))
    def test_every_day_of_the_week_is_inside(self, offset: int) -> None:
        assert check_inside_week(week(workout(offset)), context()) == []

    @pytest.mark.parametrize("offset", [-1, 7, 8, -30, 400])
    def test_other_days_are_outside(self, offset: int) -> None:
        assert check_inside_week(week(workout(offset)), context()) == [
            Finding(
                Severity.ERROR,
                "outside_week",
                "The workout does not lie within the week of the plan.",
                "workouts[0].day",
            )
        ]

    def test_each_workout_outside_is_named_by_its_place(self) -> None:
        plan = week(workout(1), workout(9), workout(2), workout(-2))

        paths = [finding.path for finding in check_inside_week(plan, context())]

        assert paths == ["workouts[1].day", "workouts[3].day"]

    def test_an_empty_plan_is_inside(self) -> None:
        assert check_inside_week(week(), context()) == []

    def test_a_context_for_another_week_is_a_programming_error(self) -> None:
        with pytest.raises(ValueError, match="another week"):
            check_inside_week(week(), context(week_start=day(7)))


class TestTheSegmentsAddUp:
    def seg(self, seconds: int, repeat: int = 1) -> Segment:
        return Segment(SegmentKind.WORK, seconds, repeat)

    def test_a_workout_without_segments_has_nothing_to_add_up(self) -> None:
        assert check_segments_add_up(week(workout(minutes=60)), context()) == []

    def test_segments_that_match_exactly_are_fine(self) -> None:
        plan = week(workout(minutes=60, segments=(self.seg(600), self.seg(300, 10))))

        assert check_segments_add_up(plan, context()) == []

    def test_repeats_count(self) -> None:
        plan = week(workout(minutes=60, segments=(self.seg(300, 12),)))

        assert check_segments_add_up(plan, context()) == []

    @pytest.mark.parametrize("difference", [-60, -1, 0, 1, 60])
    def test_a_difference_of_up_to_a_minute_is_fine(self, difference: int) -> None:
        plan = week(workout(minutes=60, segments=(self.seg(3600 + difference),)))

        assert check_segments_add_up(plan, context()) == []

    @pytest.mark.parametrize("difference", [-61, -600, 61, 3600])
    def test_a_larger_difference_is_an_error(self, difference: int) -> None:
        plan = week(workout(minutes=60, segments=(self.seg(3600 + difference),)))

        assert check_segments_add_up(plan, context()) == [
            Finding(
                Severity.ERROR,
                "segments_mismatch",
                f"The segments add up to {3600 + difference} seconds, "
                "the workout says 3600 seconds.",
                "workouts[0].segments",
            )
        ]

    def test_the_tolerance_is_a_minute(self) -> None:
        assert DURATION_TOLERANCE_SECONDS == 60

    def test_each_workout_is_judged_on_its_own(self) -> None:
        plan = week(
            workout(minutes=60, segments=(self.seg(3600),)),
            workout(2, minutes=30, segments=(self.seg(3600),)),
            workout(3, minutes=60),
        )

        assert [f.path for f in check_segments_add_up(plan, context())] == ["workouts[1].segments"]


class TestTheZoneSystems:
    @pytest.mark.parametrize(
        ("sport", "system"),
        [
            (Sport.CYCLING, ZoneSystem.POWER),
            (Sport.CYCLING, ZoneSystem.HEART_RATE),
            (Sport.RUNNING, ZoneSystem.PACE),
            (Sport.RUNNING, ZoneSystem.HEART_RATE),
        ],
    )
    def test_a_fitting_system_the_athlete_can_use_is_fine(
        self, sport: Sport, system: ZoneSystem
    ) -> None:
        plan = week(workout(sport=sport, zone_system=system, zone=2))

        assert check_zone_systems(plan, context()) == []

    @pytest.mark.parametrize(
        ("sport", "system", "message"),
        [
            (Sport.CYCLING, ZoneSystem.PACE, "Pace zones do not apply to cycling."),
            (Sport.RUNNING, ZoneSystem.POWER, "Power zones do not apply to running."),
            (Sport.SWIMMING, ZoneSystem.HEART_RATE, "Heart rate zones do not apply to swimming."),
            (Sport.SWIMMING, ZoneSystem.PACE, "Pace zones do not apply to swimming."),
            (Sport.STRENGTH, ZoneSystem.POWER, "Power zones do not apply to strength."),
        ],
    )
    def test_a_system_that_does_not_fit_the_sport_is_an_error(
        self, sport: Sport, system: ZoneSystem, message: str
    ) -> None:
        plan = week(workout(sport=sport, zone_system=system, zone=2))

        assert check_zone_systems(plan, context()) == [
            Finding(Severity.ERROR, "zone_system_not_for_sport", message, "workouts[0].zone_system")
        ]

    def test_the_table_of_systems_per_sport_is_the_documented_one(self) -> None:
        assert SPORT_ZONE_SYSTEMS == {
            Sport.CYCLING: {ZoneSystem.POWER, ZoneSystem.HEART_RATE},
            Sport.RUNNING: {ZoneSystem.PACE, ZoneSystem.HEART_RATE},
            Sport.SWIMMING: frozenset(),
            Sport.STRENGTH: frozenset(),
        }

    @pytest.mark.parametrize(
        ("sport", "system", "message"),
        [
            (
                Sport.CYCLING,
                ZoneSystem.POWER,
                "The athlete has no threshold for power zones in cycling.",
            ),
            (
                Sport.RUNNING,
                ZoneSystem.PACE,
                "The athlete has no threshold for pace zones in running.",
            ),
            (
                Sport.RUNNING,
                ZoneSystem.HEART_RATE,
                "The athlete has no threshold for heart rate zones in running.",
            ),
        ],
    )
    def test_a_system_without_a_threshold_is_an_error(
        self, sport: Sport, system: ZoneSystem, message: str
    ) -> None:
        plan = week(workout(sport=sport, zone_system=system, zone=2))

        found = check_zone_systems(plan, context(zone_systems=frozenset()))

        assert found == [
            Finding(Severity.ERROR, "zone_system_unavailable", message, "workouts[0].zone_system")
        ]

    def test_a_threshold_of_one_sport_does_not_serve_the_other(self) -> None:
        only_cycling_power = frozenset({(Sport.CYCLING, ZoneSystem.POWER)})
        plan = week(
            workout(1, sport=Sport.CYCLING, zone_system=ZoneSystem.POWER, zone=2),
            workout(2, sport=Sport.RUNNING, zone_system=ZoneSystem.HEART_RATE, zone=2),
        )

        found = check_zone_systems(plan, context(zone_systems=only_cycling_power))

        assert [f.path for f in found] == ["workouts[1].zone_system"]

    def test_the_same_system_of_another_sport_does_not_serve(self) -> None:
        # heart rate zones are known for cycling only; a run in heart rate zones has no basis
        heart_rate_for_riding = frozenset({(Sport.CYCLING, ZoneSystem.HEART_RATE)})
        plan = week(
            workout(1, sport=Sport.CYCLING, zone_system=ZoneSystem.HEART_RATE, zone=2),
            workout(2, sport=Sport.RUNNING, zone_system=ZoneSystem.HEART_RATE, zone=2),
        )

        found = check_zone_systems(plan, context(zone_systems=heart_rate_for_riding))

        assert [(f.code, f.path) for f in found] == [
            ("zone_system_unavailable", "workouts[1].zone_system")
        ]

    def test_a_workout_without_a_zone_needs_no_threshold(self) -> None:
        plan = week(workout(sport=Sport.SWIMMING), workout(2, sport=Sport.STRENGTH))

        assert check_zone_systems(plan, context(zone_systems=frozenset())) == []

    def test_the_zone_of_a_segment_is_checked_too(self) -> None:
        plan = week(
            workout(
                sport=Sport.RUNNING,
                segments=(
                    Segment(SegmentKind.WARMUP, 600, 1, ZoneSystem.PACE, 1),
                    Segment(SegmentKind.WORK, 300, 4, ZoneSystem.POWER, 4),
                    Segment(SegmentKind.WORK, 300, 4, ZoneSystem.HEART_RATE, 4),
                ),
            )
        )

        found = check_zone_systems(
            plan, context(zone_systems=frozenset({(Sport.RUNNING, ZoneSystem.PACE)}))
        )

        assert [(f.code, f.path) for f in found] == [
            ("zone_system_not_for_sport", "workouts[0].segments[1].zone_system"),
            ("zone_system_unavailable", "workouts[0].segments[2].zone_system"),
        ]

    def test_the_workout_and_its_segments_are_reported_separately(self) -> None:
        plan = week(
            workout(
                zone_system=ZoneSystem.PACE,
                zone=2,
                segments=(Segment(SegmentKind.WORK, 3600, 1, ZoneSystem.PACE, 2),),
            )
        )

        found = check_zone_systems(plan, context())

        assert [f.path for f in found] == [
            "workouts[0].zone_system",
            "workouts[0].segments[0].zone_system",
        ]


class TestTheDay:
    def test_a_day_that_fits_is_fine(self) -> None:
        plan = week(workout(1, 60), workout(1, 60))

        assert check_day_capacity(plan, context()) == []

    def test_one_minute_more_than_the_day_offers_is_an_error(self) -> None:
        plan = week(workout(1, 60), workout(1, 61))

        assert check_day_capacity(plan, context()) == [
            Finding(
                Severity.ERROR,
                "day_over_capacity",
                "Tuesday offers 120 minutes, the workouts of the day add up to 121 minutes.",
                "workouts[1]",
            )
        ]

    def test_the_workout_that_tips_the_day_is_named_and_only_once(self) -> None:
        plan = week(workout(0, 100), workout(0, 30), workout(0, 30))

        found = check_day_capacity(plan, context())

        assert [f.path for f in found] == ["workouts[1]"]

    def test_findings_come_day_by_day_and_name_the_workout_that_tips_each_day(self) -> None:
        # Monday: 30 + 100 > 120 tips at the third entry; Thursday: 200 > 120 at the second
        plan = week(workout(0, 30), workout(3, 200), workout(0, 100))

        found = check_day_capacity(plan, context())

        assert [f.path for f in found] == ["workouts[2]", "workouts[1]"]

    def test_every_day_is_judged_by_its_own_capacity(self) -> None:
        minutes = (60, 0, 120, 30, 0, 0, 240)
        plan = week(
            workout(0, 60),
            workout(1, 1),
            workout(2, 120),
            workout(3, 31),
            workout(6, 240),
        )

        found = check_day_capacity(plan, context(minutes=minutes))

        assert [(f.path, f.message[:9]) for f in found] == [
            ("workouts[1]", "Tuesday o"),
            ("workouts[3]", "Thursday "),
        ]

    def test_a_day_that_offers_nothing_says_so(self) -> None:
        found = check_day_capacity(week(workout(4, 30)), context(minutes=(0,) * 7))

        assert found == [
            Finding(
                Severity.ERROR,
                "day_over_capacity",
                "Friday offers 0 minutes, the workouts of the day add up to 30 minutes.",
                "workouts[0]",
            )
        ]

    @pytest.mark.parametrize(
        ("kind", "text"),
        [
            ("illness", "an illness"),
            ("vacation", "a vacation"),
            ("other", "a time of absence"),
            ("something_new", "a time of absence"),
        ],
    )
    def test_a_workout_in_an_absence_names_it(self, kind: str, text: str) -> None:
        absences = (None, None, kind, None, None, None, None)

        found = check_day_capacity(
            week(workout(2, 30)),
            context(absences=absences, minutes=(120, 120, 0, 120, 120, 120, 120)),
        )

        assert found == [
            Finding(
                Severity.ERROR,
                "day_in_absence",
                f"Wednesday lies within {text}; no training is possible.",
                "workouts[0]",
            )
        ]

    def test_every_workout_on_an_absence_day_is_named(self) -> None:
        absences = ("illness",) + (None,) * 6
        plan = week(workout(0, 10), workout(1, 10), workout(0, 10))

        found = check_day_capacity(plan, context(absences=absences, minutes=(0,) + (120,) * 6))

        assert [(f.code, f.path) for f in found] == [
            ("day_in_absence", "workouts[0]"),
            ("day_in_absence", "workouts[2]"),
        ]

    def test_an_absence_day_without_workouts_is_fine(self) -> None:
        absences = ("vacation",) * 7

        assert check_day_capacity(week(), context(absences=absences, minutes=(0,) * 7)) == []

    def test_workouts_outside_the_week_are_not_the_business_of_this_check(self) -> None:
        plan = week(workout(8, 999), workout(-1, 999))

        assert check_day_capacity(plan, context()) == []

    def test_the_weekday_is_named_by_its_place_in_the_week(self) -> None:
        names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        for offset, name in enumerate(names):
            found = check_day_capacity(week(workout(offset, 999)), context())
            assert found[0].message.startswith(f"{name} offers"), name


class TestTheWeek:
    def test_a_week_that_fits_is_fine(self) -> None:
        plan = week(*(workout(d, 120) for d in range(7)))

        assert check_week_capacity(plan, context()) == []

    def test_an_empty_week_is_fine(self) -> None:
        assert check_week_capacity(week(), context(weekly_minutes=0)) == []

    def test_one_minute_more_than_the_week_offers_is_an_error(self) -> None:
        plan = week(workout(0, 120), workout(1, 120), workout(2, 61))

        found = check_week_capacity(plan, context(weekly_minutes=300))

        assert found == [
            Finding(
                Severity.ERROR,
                "week_over_capacity",
                "The week adds up to 301 minutes; the user offers 300 minutes.",
                "workouts",
            )
        ]

    def test_a_weekly_budget_below_the_sum_of_the_days_is_named(self) -> None:
        plan = week(workout(0, 100), workout(1, 100), workout(2, 100))

        found = check_week_capacity(
            plan, context(weekly_budget=250, weekly_minutes=250, minutes=(100,) * 7)
        )

        assert found[0].message == (
            "The week adds up to 300 minutes; the user offers 250 minutes "
            "with the weekly budget of 250 minutes."
        )

    def test_a_budget_above_the_sum_of_the_days_is_not_mentioned(self) -> None:
        plan = week(workout(0, 100), workout(1, 100), workout(2, 100))

        found = check_week_capacity(
            plan, context(weekly_budget=5000, weekly_minutes=200, minutes=(100, 100, 0, 0, 0, 0, 0))
        )

        assert "budget" not in found[0].message

    def test_workouts_outside_the_week_do_not_count(self) -> None:
        plan = week(workout(0, 100), workout(9, 5000), workout(-3, 5000))

        assert check_week_capacity(plan, context(weekly_minutes=100)) == []


class TestAllTogether:
    def test_the_checks_are_listed_in_a_fixed_order(self) -> None:
        assert BASIC_CHECKS == (
            check_inside_week,
            check_segments_add_up,
            check_zone_systems,
            check_day_capacity,
            check_week_capacity,
        )

    def test_a_good_plan_has_no_findings(self) -> None:
        plan = week(
            workout(
                1,
                90,
                zone_system=ZoneSystem.POWER,
                zone=2,
                segments=(Segment(SegmentKind.STEADY, 5400, 1, ZoneSystem.POWER, 2),),
            ),
            workout(3, 60, sport=Sport.RUNNING, zone_system=ZoneSystem.PACE, zone=3),
        )

        assert basic_checks(plan, context()) == []

    def test_findings_come_check_by_check(self) -> None:
        plan = week(
            workout(9, 60),  # outside the week
            workout(1, 60, segments=(Segment(SegmentKind.WORK, 60),)),  # segments differ
            workout(2, 60, sport=Sport.SWIMMING, zone_system=ZoneSystem.POWER, zone=2),
            workout(3, 500),  # too long for the day and the week
        )

        found = basic_checks(plan, context(weekly_minutes=300))

        assert codes(found) == [
            "outside_week",
            "segments_mismatch",
            "zone_system_not_for_sport",
            "day_over_capacity",
            "week_over_capacity",
        ]

    def test_a_week_in_hospital_collects_every_reason(self) -> None:
        absences = ("illness",) * 3 + (None,) * 4
        plan = week(workout(0, 60), workout(1, 60), workout(5, 90))

        found = basic_checks(plan, context(absences=absences, minutes=(0, 0, 0, 90, 90, 90, 90)))

        assert codes(found) == ["day_in_absence", "day_in_absence"]

    def test_the_findings_do_not_depend_on_the_order_of_a_second_run(self) -> None:
        plan = week(workout(9, 60), workout(1, 999))
        ctx = context()

        assert basic_checks(plan, ctx) == basic_checks(plan, ctx)

    def test_a_finding_cannot_be_changed(self) -> None:
        finding = Finding(Severity.ERROR, "code", "message", "path")

        with pytest.raises(AttributeError):
            setattr(finding, "code", "other")  # noqa: B010

    def test_the_severities_are_error_and_warning(self) -> None:
        assert [s.value for s in Severity] == ["error", "warning"]


class TestNothingTheCoachWroteIsRepeated:
    MARKER = "SECRET-TITLE-MARKER"

    def test_no_message_holds_a_title_or_a_note(self) -> None:
        plan = week(
            workout(9, 999, title=self.MARKER, notes=self.MARKER),
            workout(
                1,
                999,
                title=self.MARKER,
                notes=self.MARKER,
                segments=(Segment(SegmentKind.WORK, 5),),
            ),
            workout(
                2,
                999,
                title=self.MARKER,
                sport=Sport.SWIMMING,
                zone_system=ZoneSystem.POWER,
                zone=2,
            ),
        )

        found = basic_checks(plan, context(weekly_minutes=10))

        assert found
        assert all(self.MARKER not in f.message and self.MARKER not in f.path for f in found)


class TestWhateverIsPlanned:
    def random_plan(self, rng: random.Random) -> WeekPlan:
        workouts = []
        for _ in range(rng.randint(0, 10)):
            system = rng.choice([None, *ZoneSystem])
            segments = tuple(
                Segment(
                    rng.choice(list(SegmentKind)),
                    rng.randint(1, 20_000),
                    rng.randint(1, 50),
                    rng.choice([None, *ZoneSystem]),
                    None,
                )
                for _ in range(rng.randint(0, 4))
            )
            workouts.append(
                Workout(
                    day=day(rng.randint(-10, 20)),
                    sport=rng.choice(list(Sport)),
                    title="t",
                    goal=rng.choice(list(Goal)),
                    duration_minutes=rng.randint(1, 1440),
                    segments=segments,
                    zone_system=system,
                    zone=None if system is None else 2,
                )
            )
        return week(*workouts)

    def random_context(self, rng: random.Random) -> PlanContext:
        minutes = tuple(rng.randint(0, 600) for _ in range(7))
        return context(
            minutes=minutes,
            absences=tuple(
                rng.choice([None, None, "illness", "vacation", "other", "x"]) for _ in range(7)
            ),
            weekly_budget=rng.choice([None, 100, 5000]),
            weekly_minutes=rng.randint(0, 3000),
            zone_systems=frozenset(rng.sample(sorted(ALL_SYSTEMS), rng.randint(0, 4))),
        )

    def test_no_check_raises_on_any_plan_and_the_findings_are_well_formed(self) -> None:
        rng = random.Random(20261113)
        total = 0

        for _ in range(1500):
            plan, ctx = self.random_plan(rng), self.random_context(rng)
            found = basic_checks(plan, ctx)
            total += len(found)

            assert found == basic_checks(plan, ctx)
            for finding in found:
                assert finding.severity is Severity.ERROR
                assert finding.code and finding.message and finding.path.startswith("workouts")

        assert total > 1000  # the checks are exercised, not silent


class TestThePurityOfTheModule:
    def test_the_module_reads_no_database(self) -> None:
        source = Path(rules.__file__).read_text()
        imported = {
            node.module.split(".")[0]
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.ImportFrom) and node.module
        }

        assert "django" not in imported
