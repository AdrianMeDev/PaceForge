from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from accounts.models import User
from activities.models import Activity
from athletes.models import AthleteProfile, ThresholdValue
from availability.models import AvailabilitySettings, UnavailablePeriod, WeekdayMinutes
from planning.context import (
    RECENT_WEEKS,
    PlanContext,
    build_context,
    recent_weekly_minutes,
    usable_zone_systems,
)
from planning.schema import Sport, ZoneSystem

pytestmark = pytest.mark.django_db

MONDAY = date(2027, 7, 19)
assert MONDAY.weekday() == 0
BERLIN = ZoneInfo("Europe/Berlin")
LOS_ANGELES = ZoneInfo("America/Los_Angeles")
Source = ThresholdValue.Source


@pytest.fixture
def alice() -> User:
    return User.objects.create_user("alice@example.com")


@pytest.fixture
def bob() -> User:
    return User.objects.create_user("bob@example.com")


def at(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


def done(start: str, timer: float | None = 3600, elapsed: float | None = None) -> Any:
    return (at(start), timer, elapsed)


class TestTheZoneSystemsThatCanBeUsed:
    @pytest.mark.parametrize(
        ("held", "expected"),
        [
            ([], set()),
            ([("ride", "ftp")], {(Sport.CYCLING, ZoneSystem.POWER)}),
            ([("ride", "lthr")], {(Sport.CYCLING, ZoneSystem.HEART_RATE)}),
            ([("ride", "max_hr")], {(Sport.CYCLING, ZoneSystem.HEART_RATE)}),
            ([("run", "threshold_pace")], {(Sport.RUNNING, ZoneSystem.PACE)}),
            ([("run", "lthr")], {(Sport.RUNNING, ZoneSystem.HEART_RATE)}),
            ([("run", "max_hr")], {(Sport.RUNNING, ZoneSystem.HEART_RATE)}),
            (
                [("ride", "ftp"), ("ride", "lthr"), ("ride", "max_hr")],
                {(Sport.CYCLING, ZoneSystem.POWER), (Sport.CYCLING, ZoneSystem.HEART_RATE)},
            ),
            (
                [("run", "threshold_pace"), ("run", "lthr")],
                {(Sport.RUNNING, ZoneSystem.PACE), (Sport.RUNNING, ZoneSystem.HEART_RATE)},
            ),
        ],
    )
    def test_each_threshold_opens_its_zone_system(
        self, held: list[tuple[str, str]], expected: set[tuple[Sport, ZoneSystem]]
    ) -> None:
        assert usable_zone_systems(held) == expected

    def test_a_threshold_of_one_sport_opens_nothing_for_the_other(self) -> None:
        # a cyclist's FTP says nothing about running, and a runner's pace nothing about riding
        assert usable_zone_systems([("ride", "ftp")]) == {(Sport.CYCLING, ZoneSystem.POWER)}
        assert usable_zone_systems([("run", "threshold_pace")]) == {
            (Sport.RUNNING, ZoneSystem.PACE)
        }
        assert usable_zone_systems([("ride", "threshold_pace"), ("run", "ftp")]) == set()

    def test_swimming_and_strength_never_have_zones(self) -> None:
        everything = [
            ("ride", "ftp"),
            ("ride", "lthr"),
            ("ride", "max_hr"),
            ("run", "threshold_pace"),
            ("run", "lthr"),
            ("run", "max_hr"),
        ]

        sports = {sport for sport, _ in usable_zone_systems(everything)}

        assert sports == {Sport.CYCLING, Sport.RUNNING}

    def test_it_accepts_a_one_shot_iterable_with_the_match_last(self) -> None:
        result = usable_zone_systems(iter([("run", "lthr"), ("ride", "ftp")]))

        assert result == {
            (Sport.RUNNING, ZoneSystem.HEART_RATE),
            (Sport.CYCLING, ZoneSystem.POWER),
        }

    def test_it_accepts_any_iterable_once(self) -> None:
        assert usable_zone_systems(iter([("ride", "ftp")])) == {(Sport.CYCLING, ZoneSystem.POWER)}


class TestTheRecentWeeks:
    def minutes(self, activities: list[Any], zone: Any = UTC) -> tuple[int, ...]:
        return recent_weekly_minutes(activities, zone, MONDAY)

    def test_no_activities_give_no_reference(self) -> None:
        assert self.minutes([]) == ()

    def test_activities_are_added_up_per_week_latest_week_first(self) -> None:
        result = self.minutes(
            [
                done("2027-07-12T08:00", 3600),  # the week of 12 July
                done("2027-07-14T08:00", 1800),
                done("2027-07-05T08:00", 7200),  # the week of 5 July
                done("2027-06-21T08:00", 600),  # the week of 21 June
            ]
        )

        assert result == (90, 120, 10)

    def test_the_timer_time_counts_and_the_elapsed_time_stands_in(self) -> None:
        result = self.minutes(
            [
                done("2027-07-12T08:00", timer=3000, elapsed=9999),
                done("2027-07-13T08:00", timer=None, elapsed=1200),
            ]
        )

        assert result == (70,)

    def test_a_timer_of_zero_counts_as_zero_and_does_not_fall_back(self) -> None:
        assert self.minutes([done("2027-07-12T08:00", timer=0, elapsed=3600)]) == (0,)

    def test_an_activity_without_any_duration_does_not_count_at_all(self) -> None:
        assert self.minutes([done("2027-07-12T08:00", None, None)]) == ()

    def test_a_week_with_only_such_activities_is_left_out(self) -> None:
        result = self.minutes(
            [done("2027-07-12T08:00", None, None), done("2027-07-05T08:00", 3600)]
        )

        assert result == (60,)

    def test_a_week_without_activities_is_left_out_not_counted_as_zero(self) -> None:
        result = self.minutes([done("2027-07-12T08:00", 3600), done("2027-06-28T08:00", 1800)])

        assert result == (60, 30)

    @pytest.mark.parametrize(
        ("seconds", "expected"), [(29, 0), (30, 1), (89, 1), (90, 2), (3599, 60), (3600, 60)]
    )
    def test_seconds_are_rounded_to_minutes_half_up(self, seconds: float, expected: int) -> None:
        assert self.minutes([done("2027-07-12T08:00", seconds)]) == (expected,)

    def test_the_rounding_is_done_on_the_week_not_on_each_activity(self) -> None:
        result = self.minutes([done("2027-07-12T08:00", 40), done("2027-07-13T08:00", 40)])

        assert result == (1,)  # 80 seconds, not 1 + 1

    def test_the_four_weeks_before_the_plan_make_the_window(self) -> None:
        inside = [
            done("2027-06-21T00:00", 600),  # the first moment of the window
            done("2027-07-18T23:59", 600),  # the last minute before the plan's week
        ]
        outside = [
            done("2027-06-20T23:59", 6000),  # one minute before the window
            done("2027-07-19T00:00", 6000),  # the plan's own week
            done("2027-08-01T08:00", 6000),  # later
        ]

        assert self.minutes(inside + outside) == (10, 10)

    def test_the_window_is_as_long_as_asked(self) -> None:
        activities = [done("2027-07-12T08:00", 600), done("2027-06-14T08:00", 1200)]

        assert recent_weekly_minutes(activities, UTC, MONDAY, weeks=4) == (10,)
        assert recent_weekly_minutes(activities, UTC, MONDAY, weeks=6) == (10, 20)

    def test_four_weeks_is_the_default(self) -> None:
        assert RECENT_WEEKS == 4

    def test_a_week_goes_by_the_day_in_the_time_zone_of_the_athlete(self) -> None:
        # 22:30 UTC on Sunday 11 July is 00:30 on Monday 12 July in Berlin: the next week
        activities = [
            done("2027-07-11T22:30", 3600),
            done("2027-07-13T08:00", 600),
            done("2027-07-04T22:30", 1800),
        ]

        assert self.minutes(activities, UTC) == (10, 60, 30)
        assert self.minutes(activities, BERLIN) == (70, 30)

    def test_the_plans_own_week_starts_at_local_midnight(self) -> None:
        # 22:30 UTC on Sunday 18 July is already Monday 19 July in Berlin: the plan's own week
        late = [done("2027-07-18T22:30", 3600)]

        assert self.minutes(late, UTC) == (60,)
        assert self.minutes(late, BERLIN) == ()

    def test_a_zone_behind_utc_moves_the_other_way(self) -> None:
        # 03:00 UTC on Monday 12 July is still Sunday evening 11 July in Los Angeles (UTC-7)
        activities = [done("2027-07-12T03:00", 3600), done("2027-07-14T08:00", 600)]

        assert self.minutes(activities, UTC) == (70,)
        assert self.minutes(activities, LOS_ANGELES) == (10, 60)

    def test_the_input_may_be_a_one_shot_iterable(self) -> None:
        result = recent_weekly_minutes(iter([done("2027-07-12T08:00", 3600)]), UTC, MONDAY)

        assert result == (60,)


class TestTheContextOfAUser:
    def activity(
        self, owner: User, start: str, timer: float | None = 3600, n: int = 0, **f: Any
    ) -> None:
        Activity.objects.create(
            owner=owner,
            source="fit_file",
            source_hash=f"{owner.pk}-{start}-{n}".ljust(64, "0")[:64],
            sport=f.pop("sport", "running"),
            start_time=at(start),
            timer_seconds=timer,
            elapsed_seconds=f.pop("elapsed", None),
            **f,
        )

    def held(self, owner: User, sport: str, metric: str, source: str = Source.MANUAL) -> None:
        ThresholdValue.objects.create(
            owner=owner, sport=sport, metric=metric, value=250, source=source, basis="test"
        )

    def test_a_user_with_nothing_has_an_empty_context(self, alice: User) -> None:
        context = build_context(alice, MONDAY)

        assert context == PlanContext(
            week_start=MONDAY,
            minutes=(0,) * 7,
            absences=(None,) * 7,
            weekly_budget=None,
            weekly_minutes=0,
            zone_systems=frozenset(),
            recent_weeks=(),
        )

    def test_the_week_must_start_on_a_monday(self, alice: User) -> None:
        with pytest.raises(ValueError, match="not a Monday"):
            build_context(alice, MONDAY + timedelta(days=1))

    def test_the_time_the_user_offers_comes_from_the_availability(self, alice: User) -> None:
        for weekday, minutes in enumerate([60, 0, 90, 0, 0, 120, 180]):
            WeekdayMinutes.objects.create(owner=alice, weekday=weekday, minutes=minutes)
        AvailabilitySettings.objects.create(owner=alice, weekly_budget_minutes=400)
        UnavailablePeriod.objects.create(
            owner=alice,
            kind="illness",
            start_date=MONDAY + timedelta(days=2),
            end_date=MONDAY + timedelta(days=3),
        )

        context = build_context(alice, MONDAY)

        assert context.minutes == (60, 0, 0, 0, 0, 120, 180)
        assert context.absences == (None, None, "illness", "illness", None, None, None)
        assert (context.weekly_budget, context.weekly_minutes) == (400, 360)

    @pytest.mark.parametrize("source", [Source.MANUAL, Source.INTERVALS, Source.ESTIMATED])
    def test_a_threshold_of_any_source_opens_its_zone_system(
        self, alice: User, source: str
    ) -> None:
        self.held(alice, "ride", "ftp", source)

        assert build_context(alice, MONDAY).zone_systems == {(Sport.CYCLING, ZoneSystem.POWER)}

    def test_the_zone_systems_follow_the_thresholds(self, alice: User) -> None:
        self.held(alice, "ride", "ftp")
        self.held(alice, "run", "lthr")

        assert build_context(alice, MONDAY).zone_systems == {
            (Sport.CYCLING, ZoneSystem.POWER),
            (Sport.RUNNING, ZoneSystem.HEART_RATE),
        }

    def test_the_recent_weeks_come_from_the_activities(self, alice: User) -> None:
        self.activity(alice, "2027-07-12T08:00", 3600)
        self.activity(alice, "2027-07-14T08:00", 1800, sport="cycling")
        self.activity(alice, "2027-07-05T08:00", elapsed=7200, timer=None)
        self.activity(alice, "2027-07-19T08:00", 99999)  # the plan's own week

        assert build_context(alice, MONDAY).recent_weeks == (90, 120)

    def test_the_timer_time_wins_over_the_elapsed_time_in_the_database(self, alice: User) -> None:
        self.activity(alice, "2027-07-12T08:00", 3000, elapsed=9999)

        assert build_context(alice, MONDAY).recent_weeks == (50,)

    def test_the_budget_caps_the_total_but_not_the_single_days(self, alice: User) -> None:
        for weekday in range(7):
            WeekdayMinutes.objects.create(owner=alice, weekday=weekday, minutes=60)
        AvailabilitySettings.objects.create(owner=alice, weekly_budget_minutes=200)

        context = build_context(alice, MONDAY)

        assert context.minutes == (60,) * 7
        assert (context.weekly_budget, context.weekly_minutes) == (200, 200)

    def test_the_weeks_follow_the_time_zone_of_the_profile(self, alice: User) -> None:
        self.activity(alice, "2027-07-18T22:30", 3600)  # Monday 19 July in Berlin
        self.activity(alice, "2027-07-11T22:30", 1800)  # Monday 12 July in Berlin
        AthleteProfile.objects.create(owner=alice, timezone="Europe/Berlin")

        assert build_context(alice, MONDAY).recent_weeks == (30,)

    def test_without_a_time_zone_the_weeks_are_utc(self, alice: User) -> None:
        self.activity(alice, "2027-07-18T22:30", 3600)

        assert build_context(alice, MONDAY).recent_weeks == (60,)

    def test_nothing_of_another_user_is_used(self, alice: User, bob: User) -> None:
        for weekday in range(7):
            WeekdayMinutes.objects.create(owner=bob, weekday=weekday, minutes=120)
        AvailabilitySettings.objects.create(owner=bob, weekly_budget_minutes=100)
        UnavailablePeriod.objects.create(
            owner=bob, kind="vacation", start_date=MONDAY, end_date=MONDAY
        )
        self.held(bob, "ride", "ftp")
        self.activity(bob, "2027-07-12T08:00", 3600)
        AthleteProfile.objects.create(owner=bob, timezone="Asia/Tokyo")

        assert build_context(alice, MONDAY) == PlanContext(
            MONDAY, (0,) * 7, (None,) * 7, None, 0, frozenset(), ()
        )

    def test_it_takes_six_queries_however_much_data_there_is(self, alice: User) -> None:
        with CaptureQueriesContext(connection) as empty:
            build_context(alice, MONDAY)
        for weekday in range(7):
            WeekdayMinutes.objects.create(owner=alice, weekday=weekday, minutes=60)
        AvailabilitySettings.objects.create(
            owner=alice,
            weekly_budget_minutes=300,
            typical_weekly_minutes=420,
            sports=["running", "cycling"],
            stretching=True,
        )
        for day in range(7):
            UnavailablePeriod.objects.create(
                owner=alice,
                kind="other",
                start_date=MONDAY + timedelta(days=day),
                end_date=MONDAY + timedelta(days=day),
            )
        for metric in ("ftp", "lthr", "max_hr"):
            self.held(alice, "ride", metric)
        for n in range(30):
            self.activity(alice, f"2027-07-{(n % 17) + 1:02d}T{8 + n // 17:02d}:00", 600, n=n)
        AthleteProfile.objects.create(owner=alice, timezone="Europe/Berlin")

        with CaptureQueriesContext(connection) as full:
            build_context(alice, MONDAY)

        assert len(empty) == len(full) == 6

    def test_the_typical_week_comes_from_the_settings(self, alice: User, bob: User) -> None:
        AvailabilitySettings.objects.create(owner=alice, typical_weekly_minutes=420)
        AvailabilitySettings.objects.create(owner=bob, typical_weekly_minutes=900)

        assert build_context(alice, MONDAY).typical_weekly_minutes == 420

    def test_without_a_typical_week_there_is_none(self, alice: User) -> None:
        assert build_context(alice, MONDAY).typical_weekly_minutes is None
        AvailabilitySettings.objects.create(owner=alice, weekly_budget_minutes=300)
        assert build_context(alice, MONDAY).typical_weekly_minutes is None

    def test_the_typical_week_does_not_change_what_the_week_offers(self, alice: User) -> None:
        WeekdayMinutes.objects.create(owner=alice, weekday=0, minutes=60)
        AvailabilitySettings.objects.create(owner=alice, typical_weekly_minutes=5000)

        context = build_context(alice, MONDAY)

        assert (context.weekly_minutes, context.weekly_budget) == (60, None)

    def test_the_sports_and_stretching_come_from_the_settings(self, alice: User, bob: User) -> None:
        AvailabilitySettings.objects.create(
            owner=alice, sports=["cycling", "strength"], stretching=True
        )
        AvailabilitySettings.objects.create(owner=bob, sports=["swimming"], stretching=False)

        context = build_context(alice, MONDAY)

        assert context.sports == frozenset({Sport.CYCLING, Sport.STRENGTH})
        assert context.stretching is True

    def test_without_a_choice_every_sport_is_allowed_and_stretching_is_off(
        self, alice: User
    ) -> None:
        context = build_context(alice, MONDAY)

        assert context.sports == frozenset(Sport)
        assert context.stretching is False
        AvailabilitySettings.objects.create(owner=alice, weekly_budget_minutes=300)
        assert build_context(alice, MONDAY).sports == frozenset(Sport)

    def test_the_offset_of_a_day_in_the_week(self, alice: User) -> None:
        context = build_context(alice, MONDAY)

        assert [context.offset(MONDAY + timedelta(days=d)) for d in range(7)] == list(range(7))
        assert context.offset(MONDAY - timedelta(days=1)) is None
        assert context.offset(MONDAY + timedelta(days=7)) is None
        assert context.offset(date(2000, 1, 1)) is None

    def test_the_context_cannot_be_changed(self, alice: User) -> None:
        context = build_context(alice, MONDAY)

        field = "weekly_minutes"
        with pytest.raises(FrozenInstanceError):
            setattr(context, field, 5)
