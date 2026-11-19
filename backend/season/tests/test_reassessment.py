from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest

from accounts.models import User
from athletes.models import AthleteProfile, BestTime, ThresholdValue
from availability.models import AvailabilitySettings, UnavailablePeriod, WeekdayMinutes
from goals import services as goal_services
from goals.models import Goal
from season import services
from season.inputs import skeleton_for
from season.models import SeasonPlanVersion
from season.reassessment import reassess
from season.rules import SeasonContext
from season.snapshots import collect_inputs

from .test_generation import following

pytestmark = pytest.mark.django_db

MONDAY = date(2026, 11, 16)
NOW = datetime(2026, 11, 19, 12, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(goal_services, "_utc_now", lambda: NOW)


@pytest.fixture
def alice() -> User:
    user = User.objects.create_user("alice@example.com")
    train(user)
    return user


def train(user: User, minutes: int = 60) -> None:
    for weekday in range(7):
        WeekdayMinutes.objects.create(owner=user, weekday=weekday, minutes=minutes)


def draft(user: User) -> SeasonPlanVersion:
    skeleton = skeleton_for(user)
    return services.save_draft(
        user,
        following(skeleton),
        SeasonContext(skeleton),
        input_snapshot=collect_inputs(user),
    )


def confirmed(user: User) -> SeasonPlanVersion:
    return services.confirm(user, draft(user).pk)


def race(user: User, **fields: Any) -> Goal:
    return Goal.objects.create(
        owner=user,
        **{
            "kind": "race",
            "title": "Race",
            "priority": "main",
            "target_date": MONDAY + timedelta(weeks=5),
            "discipline": "running",
            "distance_m": 10_000,
            "target_time_seconds": 2400,
            **fields,
        },
    )


def test_no_confirmed_plan_has_no_hint_even_with_changed_drafts(alice: User) -> None:
    assert reassess(alice) == {
        "confirmed_plan_id": None,
        "reasons": [],
        "deviation_weeks": [],
    }
    old = draft(alice)
    race(alice)
    assert reassess(alice)["reasons"] == []
    services.discard(alice, old.pk)
    assert reassess(alice)["confirmed_plan_id"] is None


def test_unchanged_plan_has_its_id_and_no_reasons(alice: User) -> None:
    plan = confirmed(alice)

    assert reassess(alice) == {
        "confirmed_plan_id": str(plan.pk),
        "reasons": [],
        "deviation_weeks": [],
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("title", "Changed race"),
        ("target_date", MONDAY + timedelta(weeks=6)),
        ("priority", "secondary"),
        ("discipline", "cycling"),
        ("distance_m", 21_097.5),
        ("target_time_seconds", 2500),
        ("status", "achieved"),
        ("status", "dropped"),
    ],
)
def test_meaningful_race_edits_and_status_changes(alice: User, field: str, value: Any) -> None:
    goal = race(alice)
    confirmed(alice)

    setattr(goal, field, value)
    goal.save()

    assert reassess(alice)["reasons"] == ["goals_changed"]


@pytest.mark.parametrize(("field", "value"), [("metric", "threshold_pace"), ("target_value", 310)])
def test_threshold_goal_edits(alice: User, field: str, value: Any) -> None:
    goal = Goal.objects.create(
        owner=alice, kind="threshold", title="Power", metric="ftp", target_value=300
    )
    confirmed(alice)
    setattr(goal, field, value)
    goal.save()

    assert reassess(alice)["reasons"] == ["goals_changed"]


def test_goal_kind_changes(alice: User) -> None:
    goal = race(alice)
    confirmed(alice)
    goal.kind = "general"
    goal.discipline = ""
    goal.distance_m = None
    goal.target_time_seconds = None
    goal.save()

    assert reassess(alice)["reasons"] == ["goals_changed"]


@pytest.mark.parametrize("operation", ["add", "remove", "activate"])
def test_goal_membership_changes(alice: User, operation: str) -> None:
    goal = race(alice, status="dropped" if operation == "activate" else "active")
    confirmed(alice)
    if operation == "add":
        Goal.objects.create(owner=alice, kind="general", title="Train regularly")
    elif operation == "remove":
        goal.delete()
    else:
        goal.status = "active"
        goal.save()

    assert reassess(alice)["reasons"] == ["goals_changed"]


def test_identical_saves_notes_and_inactive_goal_edits_are_ignored(alice: User) -> None:
    active = race(alice)
    inactive = race(alice, status="dropped", priority="secondary")
    best = BestTime.objects.create(owner=alice, distance="5k", seconds=1200, date=MONDAY)
    confirmed(alice)

    active.save()
    active.notes = "Changed notes"
    active.save()
    inactive.title = "Changed inactive race"
    inactive.status = "achieved"
    inactive.save()
    best.save()
    day = WeekdayMinutes.objects.for_user(alice).get(weekday=0)
    day.save()

    assert reassess(alice)["reasons"] == []


def test_effective_ftp_changes_and_overridden_values(alice: User) -> None:
    estimate = ThresholdValue.objects.create(
        owner=alice, sport="ride", metric="ftp", source="estimated", value=220
    )
    manual = ThresholdValue.objects.create(
        owner=alice, sport="ride", metric="ftp", source="manual", value=250
    )
    confirmed(alice)
    estimate.value = 260
    estimate.save()
    manual.basis = "Changed basis"
    manual.save()
    assert reassess(alice)["reasons"] == []

    manual.value = 251
    manual.save()
    assert reassess(alice)["reasons"] == ["ftp_changed"]
    manual.value = 250
    manual.save()
    estimate.value = 250
    estimate.save()
    manual.delete()
    assert reassess(alice)["reasons"] == []  # Same effective number, another source.
    estimate.delete()
    assert reassess(alice)["reasons"] == ["ftp_changed"]


def test_adding_ftp_to_an_unknown_value(alice: User) -> None:
    confirmed(alice)
    ThresholdValue.objects.create(
        owner=alice, sport="ride", metric="ftp", source="manual", value=250
    )
    assert reassess(alice)["reasons"] == ["ftp_changed"]


@pytest.mark.parametrize("operation", ["add", "remove", "distance", "seconds", "date"])
def test_best_time_changes(alice: User, operation: str) -> None:
    best = BestTime.objects.create(owner=alice, distance="5k", seconds=1200, date=MONDAY)
    confirmed(alice)
    if operation == "add":
        BestTime.objects.create(owner=alice, distance="10k", seconds=2500, date=MONDAY)
    elif operation == "remove":
        best.delete()
    else:
        value = {"distance": "10k", "seconds": 1210, "date": MONDAY - timedelta(days=1)}
        setattr(best, operation, value[operation])
        best.save()

    assert reassess(alice)["reasons"] == ["best_times_changed"]


@pytest.mark.parametrize(
    ("before", "after", "changed"),
    [
        (300, 360, True),
        (300, 359, False),
        (600, 660, False),
        (600, 719, False),
        (600, 720, True),
        (300, 240, True),
        (300, 241, False),
        (600, 480, True),
        (600, 481, False),
        (0, 59, False),
        (0, 60, True),
        (None, 60, True),
        (60, None, True),
        (None, 0, False),
    ],
)
def test_typical_minutes_require_both_thresholds(
    alice: User, before: int | None, after: int | None, changed: bool
) -> None:
    settings = AvailabilitySettings.objects.create(owner=alice, typical_weekly_minutes=before)
    confirmed(alice)
    settings.typical_weekly_minutes = after
    settings.save()

    assert reassess(alice)["reasons"] == (["training_time_changed"] if changed else [])


@pytest.mark.parametrize(
    ("before", "after", "changed"),
    [
        (300, 360, True),
        (300, 359, False),
        (600, 660, False),
        (600, 720, True),
        (300, 240, True),
        (0, 59, False),
        (0, 60, True),
    ],
)
def test_week_capacity_requires_both_thresholds(
    alice: User, before: int, after: int, changed: bool
) -> None:
    WeekdayMinutes.objects.for_user(alice).update(minutes=0)
    day = WeekdayMinutes.objects.for_user(alice).get(weekday=0)
    day.minutes = before
    day.save()
    confirmed(alice)
    day.minutes = after
    day.save()

    assert reassess(alice)["reasons"] == (["training_time_changed"] if changed else [])


def test_weekly_budget_caps_capacity_and_small_changes_do_not_count(alice: User) -> None:
    settings = AvailabilitySettings.objects.create(owner=alice, weekly_budget_minutes=300)
    confirmed(alice)
    WeekdayMinutes.objects.for_user(alice).update(minutes=100)
    assert reassess(alice)["reasons"] == []
    settings.weekly_budget_minutes = 359
    settings.save()
    assert reassess(alice)["reasons"] == []
    settings.weekly_budget_minutes = 360
    settings.save()
    assert reassess(alice)["reasons"] == ["training_time_changed"]


def test_absence_changes_compare_the_same_dates_and_only_remaining_weeks(
    alice: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    absence = UnavailablePeriod.objects.create(
        owner=alice, kind="vacation", start_date=MONDAY, end_date=MONDAY + timedelta(days=6)
    )
    confirmed(alice)
    # Advancing into a week with a different capacity does not compare it to last week's zero.
    monkeypatch.setattr(goal_services, "_utc_now", lambda: NOW + timedelta(weeks=1))
    assert reassess(alice)["reasons"] == []
    absence.delete()  # Only the completed week changes.
    assert reassess(alice)["reasons"] == []
    absence = UnavailablePeriod.objects.create(
        owner=alice,
        kind="illness",
        start_date=MONDAY + timedelta(weeks=2),
        end_date=MONDAY + timedelta(weeks=2, days=6),
    )
    assert reassess(alice)["reasons"] == ["training_time_changed"]
    absence.delete()
    assert reassess(alice)["reasons"] == []


def test_current_week_is_included_in_the_athletes_time_zone(
    alice: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    AthleteProfile.objects.create(owner=alice, timezone="America/Los_Angeles")
    confirmed(alice)
    UnavailablePeriod.objects.create(
        owner=alice, kind="vacation", start_date=MONDAY, end_date=MONDAY + timedelta(days=6)
    )
    # Monday UTC is still Sunday for the athlete: the changed week is still current.
    monkeypatch.setattr(goal_services, "_utc_now", lambda: datetime(2026, 11, 23, 1, tzinfo=UTC))
    assert reassess(alice)["reasons"] == ["training_time_changed"]
    monkeypatch.setattr(goal_services, "_utc_now", lambda: datetime(2026, 11, 23, 9, tzinfo=UTC))
    assert reassess(alice)["reasons"] == []


def test_capacity_outside_the_original_season_is_ignored(alice: User) -> None:
    confirmed(alice)  # Twelve rolling weeks.
    UnavailablePeriod.objects.create(
        owner=alice,
        kind="vacation",
        start_date=MONDAY + timedelta(weeks=12),
        end_date=MONDAY + timedelta(weeks=13),
    )
    assert reassess(alice)["reasons"] == []


def test_rollover_does_not_expire_best_times_or_goals_or_compare_a_new_frame(
    alice: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    race(alice, target_date=MONDAY + timedelta(days=6))
    BestTime.objects.create(owner=alice, distance="5k", seconds=1200, date=date(2020, 1, 1))
    plan = confirmed(alice)
    monkeypatch.setattr(goal_services, "_utc_now", lambda: NOW + timedelta(weeks=2))
    WeekdayMinutes.objects.for_user(alice).update(minutes=0)  # The season has ended.

    assert reassess(alice) == {
        "confirmed_plan_id": str(plan.pk),
        "reasons": [],
        "deviation_weeks": [],
    }


@pytest.mark.parametrize("snapshot", [None, {}, {"version": 999}])
def test_unknown_baselines_are_reported_without_inventing_history(
    alice: User, snapshot: dict[str, Any] | None
) -> None:
    plan = draft(alice)
    plan.input_snapshot = snapshot
    plan.save()
    services.confirm(alice, plan.pk)
    race(alice)

    assert reassess(alice)["reasons"] == ["baseline_unknown"]


def test_drafting_discarding_and_confirming_current_or_outdated_replacements(alice: User) -> None:
    original = confirmed(alice)
    goal = race(alice)
    hint = reassess(alice)
    assert hint["reasons"] == ["goals_changed"]
    assert hint["confirmed_plan_id"] == str(original.pk)
    replacement = draft(alice)
    assert reassess(alice) == hint
    services.discard(alice, replacement.pk)
    assert reassess(alice) == hint
    outdated = draft(alice)
    goal.target_date = MONDAY + timedelta(weeks=6)
    goal.save()
    services.confirm(alice, outdated.pk)
    assert reassess(alice) == {
        "confirmed_plan_id": str(outdated.pk),
        "reasons": ["goals_changed"],
        "deviation_weeks": [],
    }
    current = confirmed(alice)
    assert reassess(alice) == {
        "confirmed_plan_id": str(current.pk),
        "reasons": [],
        "deviation_weeks": [],
    }


def test_confirming_an_outdated_capacity_replacement_retains_the_hint(alice: User) -> None:
    confirmed(alice)
    replacement = draft(alice)
    WeekdayMinutes.objects.for_user(alice).update(minutes=120)
    services.confirm(alice, replacement.pk)
    assert reassess(alice)["reasons"] == ["training_time_changed"]
    confirmed(alice)
    assert reassess(alice)["reasons"] == []


def test_a_current_replacement_clears_the_legacy_hint(alice: User) -> None:
    legacy = draft(alice)
    legacy.input_snapshot = None
    legacy.save()
    services.confirm(alice, legacy.pk)
    assert reassess(alice)["reasons"] == ["baseline_unknown"]
    confirmed(alice)
    assert reassess(alice)["reasons"] == []


def test_multiple_reasons_have_stable_order_and_training_time_is_not_duplicated(
    alice: User,
) -> None:
    AvailabilitySettings.objects.create(owner=alice, typical_weekly_minutes=300)
    confirmed(alice)
    race(alice)
    ThresholdValue.objects.create(
        owner=alice, sport="ride", metric="ftp", source="manual", value=250
    )
    BestTime.objects.create(owner=alice, distance="5k", seconds=1200, date=MONDAY)
    AvailabilitySettings.objects.for_user(alice).update(typical_weekly_minutes=360)
    WeekdayMinutes.objects.for_user(alice).update(minutes=120)

    assert reassess(alice)["reasons"] == [
        "goals_changed",
        "ftp_changed",
        "best_times_changed",
        "training_time_changed",
    ]
