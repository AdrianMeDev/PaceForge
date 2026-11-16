from datetime import date, timedelta
from typing import Any

import pytest

from planning.context import PlanContext
from planning.rules import (
    SEASON_CHECKS,
    SEASON_WEEK_WINDOW_PERCENT,
    Finding,
    Severity,
    check_season_minutes,
    check_season_sports,
)
from planning.schema import Goal, Sport, WeekPlan, Workout
from season.schema import Focus
from season.skeleton import Phase
from season.weeks import SeasonWeekFacts

MONDAY = date(2027, 7, 12)


def workout(offset: int = 1, minutes: int = 60, sport: Sport = Sport.RUNNING) -> Workout:
    return Workout(
        day=MONDAY + timedelta(days=offset),
        sport=sport,
        title="Session",
        goal=Goal.ENDURANCE,
        duration_minutes=minutes,
    )


def week(*workouts: Workout) -> WeekPlan:
    return WeekPlan(MONDAY, tuple(workouts))


def season(*minutes: tuple[Sport, int], **fields: Any) -> SeasonWeekFacts:
    data: dict[str, Any] = {
        "week_start": MONDAY,
        "phase": Phase.BUILD,
        "recovery": False,
        "target_minutes": 300,
        "capacity_minutes": 400,
        "races": (),
        "minutes": minutes or ((Sport.RUNNING, 300),),
        "focus": Focus.ENDURANCE,
        "key_sessions": (),
        "reason": "Because.",
        **fields,
    }
    return SeasonWeekFacts(**data)


def context(facts: SeasonWeekFacts | None, **fields: Any) -> PlanContext:
    data: dict[str, Any] = {
        "week_start": MONDAY,
        "minutes": (600,) * 7,
        "absences": (None,) * 7,
        "weekly_budget": None,
        "weekly_minutes": 4200,
        "zone_systems": frozenset(),
        "recent_weeks": (),
        "season_week": facts,
        **fields,
    }
    return PlanContext(**data)


def minutes_found(plan: WeekPlan, facts: SeasonWeekFacts | None) -> list[Finding]:
    return check_season_minutes(plan, context(facts))


def sports_found(plan: WeekPlan, facts: SeasonWeekFacts | None, **fields: Any) -> list[Finding]:
    return check_season_sports(plan, context(facts, **fields))


class TestTheMinutes:
    def test_the_window_is_fifteen_percent(self) -> None:
        assert SEASON_WEEK_WINDOW_PERCENT == 15

    @pytest.mark.parametrize("planned", [255, 300, 345])
    def test_inside_the_window_nothing_is_said(self, planned: int) -> None:
        assert minutes_found(week(workout(1, planned)), season()) == []

    @pytest.mark.parametrize("planned", [254, 346, 0, 600])
    def test_outside_the_window_it_is_a_warning(self, planned: int) -> None:
        plan = week(workout(1, planned)) if planned else week()

        (finding,) = minutes_found(plan, season())

        assert finding == Finding(
            Severity.WARNING,
            "season_minutes_off",
            f"The week adds up to {planned} minutes; the season plan has 300 minutes for it "
            "(more than 15 % apart).",
            "workouts",
        )

    def test_the_edge_is_exact_and_not_rounded(self) -> None:
        facts = season((Sport.RUNNING, 101))  # 15 % of 101 is 15.15

        assert minutes_found(week(workout(1, 116)), facts) == []
        assert len(minutes_found(week(workout(1, 117)), facts)) == 1
        assert minutes_found(week(workout(1, 86)), facts) == []
        assert len(minutes_found(week(workout(1, 85)), facts)) == 1

    def test_a_season_week_of_nothing_warns_for_any_minute(self) -> None:
        facts = season((Sport.RUNNING, 0))

        assert minutes_found(week(), facts) == []
        assert len(minutes_found(week(workout(1, 1)), facts)) == 1

    def test_every_sport_counts_together(self) -> None:
        facts = season((Sport.RUNNING, 200), (Sport.CYCLING, 100))
        plan = week(workout(1, 100), workout(2, 100, Sport.CYCLING), workout(3, 80))

        assert minutes_found(plan, facts) == []

    def test_workouts_outside_the_week_do_not_count(self) -> None:
        plan = week(workout(1, 300), workout(9, 600))

        assert minutes_found(plan, season()) == []

    def test_without_a_season_week_nothing_is_checked(self) -> None:
        assert minutes_found(week(workout(1, 600)), None) == []


class TestTheSports:
    def test_a_sport_without_a_workout_is_named(self) -> None:
        facts = season((Sport.RUNNING, 200), (Sport.CYCLING, 100))

        (finding,) = sports_found(week(workout(1, 200)), facts)

        assert finding == Finding(
            Severity.WARNING,
            "season_sport_missing",
            "The season plan has 100 minutes of cycling for this week; the plan has no cycling "
            "workout.",
            "workouts",
        )

    def test_every_sport_that_is_missing_is_named_once_in_the_order_of_the_season(self) -> None:
        facts = season((Sport.RUNNING, 100), (Sport.SWIMMING, 50), (Sport.STRENGTH, 30))

        found = sports_found(week(), facts)

        assert [f.message.split(" of ")[1].split(" ")[0] for f in found] == [
            "running",
            "swimming",
            "strength",
        ]

    def test_a_workout_of_the_sport_is_enough_whatever_its_length(self) -> None:
        assert sports_found(week(workout(1, 5)), season((Sport.RUNNING, 300))) == []

    def test_a_workout_outside_the_week_is_no_workout(self) -> None:
        assert len(sports_found(week(workout(9, 60)), season())) == 1

    def test_a_sport_with_no_minutes_is_not_named(self) -> None:
        assert sports_found(week(), season((Sport.RUNNING, 0))) == []

    def test_a_sport_the_athlete_no_longer_wants_is_not_named(self) -> None:
        facts = season((Sport.RUNNING, 100), (Sport.SWIMMING, 50))

        found = sports_found(week(), facts, sports=frozenset({Sport.RUNNING}))

        assert [f.code for f in found] == ["season_sport_missing"]
        assert "running" in found[0].message

    def test_without_a_season_week_nothing_is_checked(self) -> None:
        assert sports_found(week(), None) == []


class TestTheGroup:
    def test_the_season_checks_are_these(self) -> None:
        assert SEASON_CHECKS == (check_season_minutes, check_season_sports)

    @pytest.mark.parametrize("check", SEASON_CHECKS)
    def test_they_are_warnings_only(self, check: Any) -> None:
        facts = season((Sport.SWIMMING, 100))

        found = check(week(workout(1, 500)), context(facts))

        assert found
        assert {f.severity for f in found} == {Severity.WARNING}

    @pytest.mark.parametrize("check", SEASON_CHECKS)
    def test_a_context_for_another_week_is_a_programming_error(self, check: Any) -> None:
        with pytest.raises(ValueError, match="another week"):
            check(week(), context(season(), week_start=MONDAY + timedelta(days=7)))

    def test_nothing_the_coach_wrote_is_repeated(self) -> None:
        marker = "SECRET-REASON-MARKER"
        facts = season((Sport.SWIMMING, 100), reason=marker)

        found = check_season_sports(week(), context(facts)) + check_season_minutes(
            week(workout(1, 500)), context(facts)
        )

        assert found
        assert marker not in repr(found)
