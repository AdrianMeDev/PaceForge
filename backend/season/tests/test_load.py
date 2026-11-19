from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from accounts.models import User
from planning import services as planning_services
from planning.models import PlannedWorkout, WeeklyPlan
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
)
from season.load import _season_load, planned_week_load
from season.schema import Focus, KeySession, PlanWeek, SessionKind

MONDAY = date(2026, 11, 16)


def season_week(monday: date = MONDAY) -> PlanWeek:
    return PlanWeek(monday, ((Sport.RUNNING, 120),), Focus.ENDURANCE, "Base.")


def confirmed(user: User, plan: WeekPlan) -> WeeklyPlan:
    stored = planning_services.save_draft(user, plan)
    WeeklyPlan.objects.filter(pk=stored.pk).update(
        status="confirmed", confirmed_at=datetime(2026, 11, 19, tzinfo=UTC)
    )
    stored.refresh_from_db()
    return stored


class TestSeasonEstimates:
    def test_minutes_by_sport_use_endurance_and_default_strength_rates(self) -> None:
        week = replace(season_week(), minutes=tuple((sport, 60) for sport in Sport))

        assert _season_load(week) == {"running": 55, "cycling": 55, "swimming": 55, "strength": 60}

    @pytest.mark.parametrize(
        ("kind", "rate"),
        [
            (SessionKind.LONG, 55),
            (SessionKind.TEMPO, 75),
            (SessionKind.THRESHOLD, 95),
            (SessionKind.VO2MAX, 115),
            (SessionKind.RACE_PACE, 95),
            (SessionKind.RACE, 95),
        ],
    )
    def test_key_sessions_replace_minutes_rather_than_add_them(
        self, kind: SessionKind, rate: int
    ) -> None:
        week = replace(season_week(), key_sessions=(KeySession(Sport.RUNNING, kind, 60),))

        assert _season_load(week) == {"running": 55 + rate}

    def test_each_key_session_only_changes_its_own_sport(self) -> None:
        week = replace(
            season_week(),
            minutes=((Sport.RUNNING, 120), (Sport.CYCLING, 120), (Sport.STRENGTH, 60)),
            key_sessions=(
                KeySession(Sport.RUNNING, SessionKind.TEMPO, 60),
                KeySession(Sport.RUNNING, SessionKind.THRESHOLD, 60),
                KeySession(Sport.STRENGTH, SessionKind.STRENGTH, 60),
            ),
        )

        assert _season_load(week) == {"running": 170, "cycling": 110, "strength": 60}

    def test_round_half_up_once_per_sport(self) -> None:
        week = replace(
            season_week(),
            minutes=((Sport.RUNNING, 6),),
            key_sessions=(KeySession(Sport.RUNNING, SessionKind.TEMPO, 3),),
        )

        assert _season_load(week) == {"running": 7}  # (3 * 75 + 3 * 55) / 60 = 6.5

    def test_empty_and_zero_minute_sports(self) -> None:
        assert _season_load(replace(season_week(), minutes=())) == {}
        assert _season_load(replace(season_week(), minutes=((Sport.RUNNING, 0),))) == {"running": 0}

    def test_invalid_draft_sessions_cannot_add_minutes_beyond_the_sport_budget(self) -> None:
        week = replace(
            season_week(),
            minutes=((Sport.RUNNING, 60),),
            key_sessions=(
                KeySession(Sport.RUNNING, SessionKind.TEMPO, 90),
                KeySession(Sport.RUNNING, SessionKind.VO2MAX, 60),
                KeySession(Sport.CYCLING, SessionKind.THRESHOLD, 60),
            ),
        )

        assert _season_load(week) == {"running": 75}


@pytest.mark.django_db
class TestConfirmedWeekLoad:
    @pytest.fixture
    def alice(self) -> User:
        return User.objects.create_user("alice@example.com")

    def test_confirmed_workouts_replace_the_whole_season_estimate(self, alice: User) -> None:
        confirmed(
            alice,
            WeekPlan(
                MONDAY,
                (
                    Workout(
                        MONDAY,
                        Sport.CYCLING,
                        "Ride",
                        Goal.ENDURANCE,
                        60,
                        segments=(Segment(SegmentKind.WORK, 600, 3, ZoneSystem.POWER, 4),),
                    ),
                    Workout(MONDAY, Sport.CYCLING, "Easy", Goal.ENDURANCE, 30),
                    Workout(
                        MONDAY,
                        Sport.STRENGTH,
                        "Strength",
                        Goal.STRENGTH,
                        60,
                        exercises=(
                            Exercise(
                                "Squat",
                                ExerciseRegion.LEGS,
                                ExerciseEquipment.BODYWEIGHT,
                                3,
                                reps=10,
                                rpe=8,
                            ),
                        ),
                    ),
                ),
            ),
        )

        assert planned_week_load(alice, [season_week()]) == {
            MONDAY: {"cycling": 123, "strength": 80}
        }

    def test_an_empty_confirmed_week_replaces_the_estimate(self, alice: User) -> None:
        confirmed(alice, WeekPlan(MONDAY))

        assert planned_week_load(alice, [season_week()]) == {MONDAY: {}}

    @pytest.mark.parametrize("status", ["draft", "superseded", "discarded"])
    def test_other_versions_never_override_the_season(self, alice: User, status: str) -> None:
        stored = planning_services.save_draft(
            alice, WeekPlan(MONDAY, (Workout(MONDAY, Sport.CYCLING, "Ride", Goal.ENDURANCE, 60),))
        )
        WeeklyPlan.objects.filter(pk=stored.pk).update(
            status=status,
            confirmed_at=datetime(2026, 11, 19, tzinfo=UTC) if status == "superseded" else None,
        )

        assert planned_week_load(alice, [season_week()]) == {MONDAY: {"running": 110}}

    def test_other_users_confirmed_weeks_do_not_override_the_estimate(self, alice: User) -> None:
        bob = User.objects.create_user("bob@example.com")
        confirmed(bob, WeekPlan(MONDAY))

        assert planned_week_load(alice, [season_week()]) == {MONDAY: {"running": 110}}

    def test_a_workout_owned_by_another_user_is_excluded(self, alice: User) -> None:
        bob = User.objects.create_user("bob@example.com")
        stored = confirmed(
            alice, WeekPlan(MONDAY, (Workout(MONDAY, Sport.RUNNING, "Run", Goal.THRESHOLD, 60),))
        )
        PlannedWorkout.objects.filter(plan=stored).update(owner=bob)

        assert planned_week_load(alice, [season_week()]) == {MONDAY: {}}

    @pytest.mark.parametrize("count", [1, 52])
    def test_one_query_for_many_weeks_and_workouts(self, alice: User, count: int) -> None:
        weeks = [season_week(MONDAY + timedelta(weeks=n)) for n in range(count)]
        for week in weeks[::2]:
            confirmed(
                alice,
                WeekPlan(
                    week.week_start,
                    tuple(
                        Workout(week.week_start, Sport.RUNNING, "Run", Goal.THRESHOLD, 30)
                        for _ in range(3)
                    ),
                ),
            )

        with CaptureQueriesContext(connection) as queries:
            found = planned_week_load(alice, weeks)

        assert len(queries) == 1
        assert found == {
            week.week_start: {"running": 144 if n % 2 == 0 else 110} for n, week in enumerate(weeks)
        }

    def test_no_weeks_need_no_query(self, alice: User) -> None:
        with CaptureQueriesContext(connection) as queries:
            assert planned_week_load(alice, []) == {}
        assert len(queries) == 0
