from datetime import UTC, date, datetime, time, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from accounts.models import User
from activities.models import Activity
from athletes.models import AthleteProfile
from goals import services as goal_services
from planning.models import WeeklyPlan
from reviews.services import week_summary
from reviews.tests.builders import make_activity, make_plan
from season import deviation, services
from season.deviation import deviation_weeks
from season.models import SeasonPlanVersion

from .test_reassessment import MONDAY, NOW, confirmed, draft, race, train

pytestmark = pytest.mark.django_db

WEEKS = tuple(MONDAY + timedelta(weeks=n) for n in (1, 2, 3))
CHECK_NOW = NOW + timedelta(weeks=4)


def make_season(
    user: User, monkeypatch: pytest.MonkeyPatch, confirmed_at: datetime = NOW
) -> SeasonPlanVersion:
    monkeypatch.setattr(goal_services, "_utc_now", lambda: NOW)
    monkeypatch.setattr(services, "_now", lambda: confirmed_at)
    plan = confirmed(user)
    monkeypatch.setattr(goal_services, "_utc_now", lambda: CHECK_NOW)
    monkeypatch.setattr(services, "_now", lambda: CHECK_NOW)
    return plan


def training(user: User, seconds: float = 1800, weeks: tuple[date, ...] = WEEKS) -> None:
    for monday in weeks:
        make_plan(user, monday, workouts=1)
        make_activity(user, f"{monday}T12:00", timer_seconds=seconds)


@pytest.fixture
def alice() -> User:
    user = User.objects.create_user("alice@example.com")
    train(user)
    return user


@pytest.fixture
def season(alice: User, monkeypatch: pytest.MonkeyPatch) -> SeasonPlanVersion:
    return make_season(alice, monkeypatch)


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0, True),
        (2519, True),
        (2520, False),
        (2521, False),
        (4679, False),
        (4680, False),
        (4681, True),
        (5400, True),
    ],
)
def test_all_three_weeks_must_be_strictly_outside_the_duration_bounds(
    alice: User, season: SeasonPlanVersion, seconds: float, expected: bool
) -> None:
    training(alice, seconds)

    assert deviation_weeks(alice, season) == (WEEKS if expected else ())


def test_a_week_without_activities_counts_as_zero_done(
    alice: User, season: SeasonPlanVersion
) -> None:
    for monday in WEEKS:
        make_plan(alice, monday, workouts=1)

    assert deviation_weeks(alice, season) == WEEKS


def test_each_week_can_deviate_in_either_direction(alice: User, season: SeasonPlanVersion) -> None:
    training(alice)
    Activity.objects.for_user(alice).filter(start_time__date=WEEKS[1]).update(timer_seconds=5400)

    assert deviation_weeks(alice, season) == WEEKS


@pytest.mark.parametrize("interrupted", [0, 1, 2])
def test_a_normal_week_breaks_the_sequence(
    alice: User, season: SeasonPlanVersion, interrupted: int
) -> None:
    training(alice)
    Activity.objects.for_user(alice).filter(start_time__date=WEEKS[interrupted]).update(
        timer_seconds=3600
    )

    assert deviation_weeks(alice, season) == ()


@pytest.mark.parametrize("count", [1, 2])
def test_fewer_than_three_weeks_are_insufficient(
    alice: User, season: SeasonPlanVersion, count: int
) -> None:
    training(alice, weeks=WEEKS[-count:])

    assert deviation_weeks(alice, season) == ()


@pytest.mark.parametrize("status", ["draft", "superseded", "discarded"])
def test_only_confirmed_weekly_plans_supply_planned_minutes(
    alice: User, season: SeasonPlanVersion, status: str
) -> None:
    training(alice, weeks=(WEEKS[0], WEEKS[2]))
    make_plan(alice, WEEKS[1], status=status, workouts=1)
    make_activity(alice, f"{WEEKS[1]}T12:00", timer_seconds=1800)

    assert deviation_weeks(alice, season) == ()


def test_a_confirmed_week_with_zero_planned_minutes_breaks_the_sequence(
    alice: User, season: SeasonPlanVersion
) -> None:
    training(alice, weeks=(WEEKS[0], WEEKS[2]))
    make_plan(alice, WEEKS[1])

    assert deviation_weeks(alice, season) == ()


def test_unknown_duration_even_on_an_extra_activity_breaks_the_sequence(
    alice: User, season: SeasonPlanVersion
) -> None:
    training(alice)
    make_activity(alice, f"{WEEKS[1]}T18:00", sport="cycling", timer_seconds=None)

    assert deviation_weeks(alice, season) == ()


@pytest.mark.parametrize(
    ("timer", "elapsed", "expected"),
    [(None, 1800, True), (None, 3600, False), (0, 3600, True), (1800, 3600, True)],
)
def test_timer_duration_takes_priority_with_elapsed_as_fallback(
    alice: User, season: SeasonPlanVersion, timer: float | None, elapsed: float, expected: bool
) -> None:
    training(alice)
    Activity.objects.for_user(alice).update(timer_seconds=timer, elapsed_seconds=elapsed)

    assert deviation_weeks(alice, season) == (WEEKS if expected else ())


def test_all_activities_count_including_unmatched_sports(
    alice: User, season: SeasonPlanVersion
) -> None:
    training(alice)
    for monday in WEEKS:
        make_activity(alice, f"{monday}T18:00", sport="cycling", timer_seconds=1800)

    assert deviation_weeks(alice, season) == ()


def test_other_weekly_versions_do_not_change_the_denominator(
    alice: User, season: SeasonPlanVersion
) -> None:
    training(alice, seconds=5400)
    for monday in WEEKS:
        for status in ("draft", "superseded", "discarded"):
            make_plan(alice, monday, status=status, workouts=3)

    assert deviation_weeks(alice, season) == WEEKS


def test_only_the_latest_three_completed_weeks_are_examined(
    alice: User, season: SeasonPlanVersion
) -> None:
    older = (MONDAY, *WEEKS[:2])
    training(alice, weeks=older)
    make_plan(alice, WEEKS[2], workouts=1)
    make_activity(alice, f"{WEEKS[2]}T12:00", timer_seconds=3600)
    training(alice, weeks=(MONDAY + timedelta(weeks=4),))  # Unfinished week.
    with patch.object(deviation, "week_summary", wraps=week_summary) as summaries:
        assert deviation_weeks(alice, season) == ()

    assert [call.args for call in summaries.call_args_list] == [(alice, week) for week in WEEKS]


@pytest.mark.parametrize("offset", [-1, 0, 1])
def test_the_first_week_must_start_at_or_after_the_confirmation_instant(
    alice: User, monkeypatch: pytest.MonkeyPatch, offset: int
) -> None:
    training(alice)
    confirmed_at = datetime.combine(WEEKS[0], time.min, tzinfo=UTC) + timedelta(microseconds=offset)
    season = make_season(alice, monkeypatch, confirmed_at)

    assert deviation_weeks(alice, season) == (WEEKS if offset <= 0 else ())


def test_week_dates_before_the_season_do_not_count(
    alice: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    weeks = (MONDAY - timedelta(weeks=1), MONDAY, WEEKS[0])
    training(alice, weeks=weeks)
    season = make_season(alice, monkeypatch, NOW - timedelta(weeks=3))
    monkeypatch.setattr(goal_services, "_utc_now", lambda: NOW + timedelta(weeks=2))

    assert deviation_weeks(alice, season) == ()


def test_weeks_after_the_season_ends_do_not_count_or_fall_back_to_an_older_streak(
    alice: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    race(alice, target_date=WEEKS[1] + timedelta(days=6))
    season = make_season(alice, monkeypatch)
    training(alice)

    assert deviation_weeks(alice, season) == ()


@pytest.mark.parametrize("zone_name", ["Europe/Berlin", "America/Los_Angeles"])
def test_activity_week_boundaries_follow_the_athletes_local_time(
    alice: User, season: SeasonPlanVersion, zone_name: str
) -> None:
    AthleteProfile.objects.create(owner=alice, timezone=zone_name)
    zone = ZoneInfo(zone_name)
    for monday in WEEKS:
        make_plan(alice, monday, workouts=1)
        # The final second of Sunday belongs to this week, including when UTC says Monday.
        end = datetime.combine(monday + timedelta(days=7), time.min, tzinfo=zone)
        Activity.objects.create(
            owner=alice,
            source="manual",
            sport="running",
            start_time=end - timedelta(seconds=1),
            timer_seconds=1800,
        )
    # Unknown durations just outside the three-week window must not contribute.
    start = datetime.combine(WEEKS[0], time.min, tzinfo=zone)
    for stamp in (start - timedelta(seconds=1), end):
        Activity.objects.create(owner=alice, source="manual", sport="cycling", start_time=stamp)

    assert deviation_weeks(alice, season) == WEEKS


def test_the_current_local_week_is_not_complete_until_monday(
    alice: User, season: SeasonPlanVersion, monkeypatch: pytest.MonkeyPatch
) -> None:
    AthleteProfile.objects.create(owner=alice, timezone="America/Los_Angeles")
    training(alice)
    monday = datetime(2026, 12, 14, 8, tzinfo=UTC)
    monkeypatch.setattr(goal_services, "_utc_now", lambda: monday - timedelta(microseconds=1))
    assert deviation_weeks(alice, season) == ()
    monkeypatch.setattr(goal_services, "_utc_now", lambda: monday)
    assert deviation_weeks(alice, season) == WEEKS


@pytest.mark.parametrize(("minute", "expected"), [(59, WEEKS), (61, ())])
def test_confirmation_uses_the_local_midnight_instant(
    alice: User, monkeypatch: pytest.MonkeyPatch, minute: int, expected: tuple[date, ...]
) -> None:
    AthleteProfile.objects.create(owner=alice, timezone="America/Los_Angeles")
    training(alice)
    # Confirmation on Monday UTC is still before the local week begins.
    confirmed_at = datetime.combine(WEEKS[0], time(7), tzinfo=UTC) + timedelta(minutes=minute)
    season = make_season(alice, monkeypatch, confirmed_at)
    assert deviation_weeks(alice, season) == expected


def test_another_athletes_plans_and_activities_never_contribute(
    alice: User, season: SeasonPlanVersion, monkeypatch: pytest.MonkeyPatch
) -> None:
    bob = User.objects.create_user("bob@example.com")
    train(bob)
    bob_season = make_season(bob, monkeypatch)
    training(bob)
    assert deviation_weeks(alice, season) == ()
    assert deviation_weeks(alice, bob_season) == ()
    training(alice, seconds=3600)
    assert deviation_weeks(alice, season) == ()
    assert deviation_weeks(bob, bob_season) == WEEKS
    # Bob's normal training and unknown durations cannot hide Alice's weak weeks either.
    Activity.objects.for_user(alice).update(timer_seconds=1800)
    Activity.objects.for_user(bob).update(timer_seconds=None)
    assert deviation_weeks(alice, season) == WEEKS
    WeeklyPlan.objects.for_user(alice).filter(week_start=WEEKS[1]).delete()
    assert deviation_weeks(alice, season) == ()


def test_drafts_and_superseded_seasons_cannot_supply_evidence(
    alice: User, season: SeasonPlanVersion
) -> None:
    training(alice)
    replacement = draft(alice)
    assert deviation_weeks(alice, replacement) == ()
    services.confirm(alice, replacement.pk)
    season.refresh_from_db()
    assert deviation_weeks(alice, season) == ()
