from datetime import date, timedelta
from typing import Any

import pytest

from planning.context import PlanContext
from planning.rules import (
    LONG_MATCH_PERCENT,
    SEASON_CHECKS,
    SEASON_WEEK_WINDOW_PERCENT,
    Finding,
    Severity,
    check_season_key_sessions,
    check_season_minutes,
    check_season_sports,
)
from planning.schema import Goal, Sport, WeekPlan, Workout
from season.schema import Focus, KeySession, SessionKind
from season.skeleton import Phase
from season.weeks import SeasonWeekFacts

MONDAY = date(2027, 7, 12)


def workout(
    offset: int = 1,
    minutes: int = 60,
    sport: Sport = Sport.RUNNING,
    goal: Goal = Goal.ENDURANCE,
) -> Workout:
    return Workout(
        day=MONDAY + timedelta(days=offset),
        sport=sport,
        title="Session",
        goal=goal,
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
        assert SEASON_CHECKS == (
            check_season_minutes,
            check_season_sports,
            check_season_key_sessions,
        )

    @pytest.mark.parametrize("check", SEASON_CHECKS)
    def test_they_are_warnings_only(self, check: Any) -> None:
        facts = season(
            (Sport.SWIMMING, 100),
            key_sessions=(KeySession(Sport.SWIMMING, SessionKind.LONG, 60),),
        )

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


def key(kind: SessionKind, minutes: int = 60, sport: Sport = Sport.RUNNING) -> KeySession:
    return KeySession(sport, kind, minutes, "3 x 10 min")


def keys_found(plan: WeekPlan, *sessions: KeySession, **fields: Any) -> list[Finding]:
    facts = season(key_sessions=sessions)
    return check_season_key_sessions(plan, context(facts, **fields))


class TestTheKeySessions:
    def test_a_match_for_long_is_three_quarters_of_the_minutes(self) -> None:
        assert LONG_MATCH_PERCENT == 75

    @pytest.mark.parametrize(
        ("kind", "goal"),
        [
            (SessionKind.TEMPO, Goal.TEMPO),
            (SessionKind.THRESHOLD, Goal.THRESHOLD),
            (SessionKind.VO2MAX, Goal.VO2MAX),
        ],
    )
    def test_the_goal_of_the_workout_decides_for_the_quality_kinds(
        self, kind: SessionKind, goal: Goal
    ) -> None:
        assert keys_found(week(workout(1, 45, goal=goal)), key(kind)) == []
        (finding,) = keys_found(week(workout(1, 45, goal=Goal.ENDURANCE)), key(kind))
        assert finding.code == "season_key_session_missing"

    def test_the_sport_has_to_match(self) -> None:
        plan = week(workout(1, 45, Sport.CYCLING, Goal.THRESHOLD))

        assert len(keys_found(plan, key(SessionKind.THRESHOLD))) == 1
        assert keys_found(plan, key(SessionKind.THRESHOLD, sport=Sport.CYCLING)) == []

    @pytest.mark.parametrize(("minutes", "found"), [(44, 1), (45, 0), (90, 0)])
    def test_a_long_session_is_a_workout_of_three_quarters_of_its_minutes(
        self, minutes: int, found: int
    ) -> None:
        assert len(keys_found(week(workout(1, minutes)), key(SessionKind.LONG, 60))) == found

    def test_any_strength_workout_is_a_strength_session(self) -> None:
        strength = key(SessionKind.STRENGTH, 45, Sport.STRENGTH)

        assert keys_found(week(workout(1, 10, Sport.STRENGTH)), strength) == []
        assert len(keys_found(week(workout(1, 60)), strength)) == 1

    @pytest.mark.parametrize("kind", [SessionKind.RACE, SessionKind.RACE_PACE])
    def test_a_race_and_a_race_pace_are_not_checked(self, kind: SessionKind) -> None:
        assert keys_found(week(), key(kind)) == []

    def test_one_workout_counts_for_one_key_session_only(self) -> None:
        plan = week(workout(1, 90, goal=Goal.THRESHOLD))

        found = keys_found(plan, key(SessionKind.THRESHOLD, 60), key(SessionKind.LONG, 90))

        assert len(found) == 1

    def test_the_sessions_are_matched_as_well_as_they_can_be(self) -> None:
        # the long one comes first and could take the threshold workout, which the threshold
        # session needs: with the other workout for the long one both are met
        plan = week(workout(1, 90, goal=Goal.THRESHOLD), workout(3, 90))

        assert keys_found(plan, key(SessionKind.LONG, 90), key(SessionKind.THRESHOLD, 60)) == []

    def test_the_ones_left_over_are_named_once_each_in_the_order_of_the_season(self) -> None:
        found = keys_found(
            week(),
            key(SessionKind.VO2MAX, 30),
            key(SessionKind.LONG, 120, Sport.CYCLING),
        )

        assert [f.message for f in found] == [
            "The season plan has a VO2max session of 30 minutes in running for this week; the "
            "plan has no workout for it.",
            "The season plan has a long session of 120 minutes in cycling for this week; the "
            "plan has no workout for it.",
        ]
        assert {f.path for f in found} == {"workouts"}
        assert {f.severity for f in found} == {Severity.WARNING}

    def test_workouts_outside_the_week_do_not_count(self) -> None:
        assert len(keys_found(week(workout(9, 90)), key(SessionKind.LONG, 60))) == 1

    def test_a_sport_the_athlete_no_longer_wants_is_not_named(self) -> None:
        assert keys_found(week(), key(SessionKind.LONG), sports=frozenset({Sport.CYCLING})) == []

    def test_without_key_sessions_or_a_season_week_nothing_is_said(self) -> None:
        assert keys_found(week()) == []
        assert check_season_key_sessions(week(), context(None)) == []

    def test_the_detail_of_the_coach_is_not_repeated(self) -> None:
        marker = KeySession(Sport.RUNNING, SessionKind.LONG, 60, "SECRET-DETAIL-MARKER")

        found = keys_found(week(), marker)

        assert found
        assert "SECRET-DETAIL-MARKER" not in repr(found)
