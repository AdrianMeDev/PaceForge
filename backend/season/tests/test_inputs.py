from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from accounts.models import User
from activities.models import Activity
from athletes.models import AthleteProfile
from availability.models import AvailabilitySettings, UnavailablePeriod, WeekdayMinutes
from goals import services
from goals.models import Goal
from season.inputs import races_of, reference_minutes, skeleton_for
from season.skeleton import MAX_WEEKS, Phase, Race

pytestmark = pytest.mark.django_db

# A Thursday; the Monday of its week is the 16th.
NOW = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)
MONDAY = date(2026, 11, 16)


@pytest.fixture(autouse=True)
def _fixed_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(services, "_utc_now", lambda: NOW)


@pytest.fixture
def alice() -> User:
    return User.objects.create_user("alice@example.com")


@pytest.fixture
def bob() -> User:
    return User.objects.create_user("bob@example.com")


def train(user: User, minutes: int = 60) -> None:
    for weekday in range(7):
        WeekdayMinutes.objects.create(owner=user, weekday=weekday, minutes=minutes)


def race(owner: User, weeks: int, priority: str = "secondary", **fields: Any) -> Goal:
    data: dict[str, Any] = {
        "kind": "race",
        "title": f"Race {weeks}",
        "priority": priority,
        "target_date": MONDAY + timedelta(weeks=weeks, days=6),
        "discipline": "running",
        "distance_m": 42195,
        **fields,
    }
    return Goal.objects.create(owner=owner, **data)


def done(owner: User, days_ago: int, minutes: int, n: int = 0) -> None:
    start = NOW - timedelta(days=days_ago)
    Activity.objects.create(
        owner=owner,
        source="fit_file",
        source_hash=f"{owner.pk}-{days_ago}-{n}".ljust(64, "0")[:64],
        sport="running",
        start_time=start,
        timer_seconds=minutes * 60,
    )


class TestTheRaces:
    def test_only_active_races_with_a_date_count(self, alice: User) -> None:
        race(alice, 10, "main")
        race(alice, 12, status="achieved")
        race(alice, 13, status="dropped")
        Goal.objects.create(owner=alice, kind="general", title="Fitter")
        Goal.objects.create(
            owner=alice, kind="threshold", title="FTP", metric="ftp", target_value=280,
            target_date=MONDAY + timedelta(weeks=5),
        )  # fmt: skip

        found = races_of(alice)

        assert [r.priority for r in found] == ["main"]

    def test_they_come_by_date_with_what_the_skeleton_needs(self, alice: User) -> None:
        race(alice, 20, discipline="cycling", distance_m=160_000, title="Gran Fondo")
        race(alice, 8, "preparation", distance_m=None)

        found = races_of(alice)

        assert found == (
            Race(MONDAY + timedelta(weeks=8, days=6), "preparation", "running", None, "Race 8"),
            Race(
                MONDAY + timedelta(weeks=20, days=6),
                "secondary",
                "cycling",
                160_000,
                "Gran Fondo",
            ),
        )

    def test_the_races_of_other_users_are_not_seen(self, alice: User, bob: User) -> None:
        race(bob, 10, "main")

        assert races_of(alice) == ()


class TestTheReference:
    def test_the_higher_of_the_recent_average_and_the_normal_week(self) -> None:
        assert reference_minutes((300, 200), None) == 250
        assert reference_minutes((300, 200), 400) == 400
        assert reference_minutes((300, 200), 100) == 250
        assert reference_minutes((), 400) == 400

    def test_without_either_there_is_none(self) -> None:
        assert reference_minutes((), None) is None
        assert reference_minutes((), 0) is None
        assert reference_minutes((0, 0), None) is None

    def test_it_is_a_whole_number_rounded_half_up(self) -> None:
        assert reference_minutes((101, 100), None) == 101  # 100.5
        assert reference_minutes((100, 100, 101), None) == 100  # 100.33


class TestTheSkeleton:
    def test_a_user_without_goals_has_the_rolling_skeleton_from_this_week(
        self, alice: User
    ) -> None:
        skeleton = skeleton_for(alice)

        assert skeleton.rolling is True
        assert skeleton.weeks[0].week_start == MONDAY
        assert len(skeleton.weeks) == 12

    def test_it_runs_to_the_week_of_the_race(self, alice: User) -> None:
        train(alice)
        race(alice, 14, "main")

        skeleton = skeleton_for(alice)

        assert len(skeleton.weeks) == 15
        assert skeleton.main_race is not None
        assert skeleton.main_race.title == "Race 14"
        assert skeleton.weeks[-1].phase is Phase.TAPER
        assert skeleton.weeks[-1].races[0].title == "Race 14"

    def test_the_weeks_offer_what_the_availability_says(self, alice: User) -> None:
        train(alice, 60)
        UnavailablePeriod.objects.create(
            owner=alice,
            kind="vacation",
            start_date=MONDAY + timedelta(weeks=2),
            end_date=MONDAY + timedelta(weeks=2, days=6),
        )
        AvailabilitySettings.objects.create(owner=alice, weekly_budget_minutes=300)
        race(alice, 10, "main")

        skeleton = skeleton_for(alice)

        assert [w.capacity_minutes for w in skeleton.weeks[:4]] == [300, 300, 0, 300]
        assert skeleton.weeks[2].target_minutes == 0

    def test_the_start_is_the_recent_average(self, alice: User) -> None:
        train(alice, 120)
        for week in (1, 2):
            done(alice, 7 * week - 1, 200, n=week)
        race(alice, 10, "main")

        assert skeleton_for(alice).weeks[0].target_minutes == 200

    def test_the_normal_week_counts_if_it_is_higher(self, alice: User) -> None:
        train(alice, 120)
        done(alice, 6, 200)
        AvailabilitySettings.objects.create(owner=alice, typical_weekly_minutes=500)
        race(alice, 10, "main")

        assert skeleton_for(alice).weeks[0].target_minutes == 500

    def test_without_history_the_start_is_half_of_the_first_week(self, alice: User) -> None:
        train(alice, 60)
        race(alice, 10, "main")

        assert skeleton_for(alice).weeks[0].target_minutes == 210

    def test_the_intensity_level_sets_the_ramp(self, alice: User) -> None:
        train(alice, 1000)
        AvailabilitySettings.objects.create(
            owner=alice, intensity_level="intensive", typical_weekly_minutes=1000
        )
        race(alice, 20, "main")

        first, second = skeleton_for(alice).weeks[:2]

        assert second.target_minutes == round(first.target_minutes * 1.10)

    def test_the_default_level_is_normal(self, alice: User) -> None:
        train(alice, 1000)
        AvailabilitySettings.objects.create(owner=alice, typical_weekly_minutes=1000)
        race(alice, 20, "main")

        first, second = skeleton_for(alice).weeks[:2]

        assert second.target_minutes == round(first.target_minutes * 1.08)

    def test_today_is_the_day_in_the_time_zone_of_the_athlete(
        self, alice: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Sunday night in UTC is already Monday in Tokyo
        sunday = datetime(2026, 11, 22, 23, 30, tzinfo=UTC)
        monkeypatch.setattr(services, "_utc_now", lambda: sunday)
        AthleteProfile.objects.create(owner=alice, timezone="Asia/Tokyo")

        assert skeleton_for(alice).weeks[0].week_start == date(2026, 11, 23)

    def test_the_data_of_other_users_is_not_used(self, alice: User, bob: User) -> None:
        train(bob, 600)
        race(bob, 10, "main")
        done(bob, 6, 900)
        AvailabilitySettings.objects.create(owner=bob, typical_weekly_minutes=900)

        skeleton = skeleton_for(alice)

        assert skeleton.rolling is True
        assert {w.capacity_minutes for w in skeleton.weeks} == {0}

    def test_a_race_beyond_a_year_is_cut_off(self, alice: User) -> None:
        train(alice)
        race(alice, 80, "main")

        skeleton = skeleton_for(alice)

        assert len(skeleton.weeks) == MAX_WEEKS
        assert skeleton.truncated is True

    def test_it_takes_the_same_queries_whatever_there_is(self, alice: User) -> None:
        with CaptureQueriesContext(connection) as empty:
            skeleton_for(alice)
        train(alice)
        AvailabilitySettings.objects.create(
            owner=alice, weekly_budget_minutes=400, typical_weekly_minutes=300
        )
        AthleteProfile.objects.create(owner=alice, timezone="Europe/Berlin")
        for number in range(8):
            race(alice, 5 + number * 4, "main" if number == 2 else "secondary")
        for number in range(30):
            done(alice, number, 45, n=number)
        UnavailablePeriod.objects.create(
            owner=alice, kind="vacation", start_date=MONDAY, end_date=MONDAY + timedelta(days=40)
        )

        with CaptureQueriesContext(connection) as full:
            skeleton_for(alice)

        assert len(empty) == len(full) == 8
