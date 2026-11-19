import json
from datetime import date

import pytest

from accounts.models import User
from athletes.models import BestTime, ThresholdValue
from availability.models import AvailabilitySettings
from goals.models import Goal
from season.snapshots import collect_inputs

pytestmark = pytest.mark.django_db

DAY = date(2026, 11, 16)


@pytest.fixture
def alice() -> User:
    return User.objects.create_user("alice@example.com")


def test_missing_inputs_are_explicit_and_collection_does_not_create_rows(alice: User) -> None:
    assert collect_inputs(alice) == {
        "version": 1,
        "goals": [],
        "ftp": None,
        "best_times": [],
        "typical_weekly_minutes": None,
    }
    assert not AvailabilitySettings.objects.exists()
    assert not ThresholdValue.objects.exists()


def test_active_goals_keep_their_inputs_in_id_order_without_notes_or_timestamps(
    alice: User,
) -> None:
    race = Goal.objects.create(
        owner=alice,
        kind="race",
        title="Race",
        priority="main",
        target_date=DAY,
        discipline="running",
        distance_m=10_000,
        target_time_seconds=2400,
        notes="Private notes",
    )
    threshold = Goal.objects.create(
        owner=alice, kind="threshold", title="Power", metric="ftp", target_value=300
    )
    general = Goal.objects.create(owner=alice, kind="general", title="Keep training")
    for status in ("achieved", "dropped"):
        Goal.objects.create(owner=alice, kind="general", title="Old", status=status)

    snapshot = collect_inputs(alice)

    assert [goal["id"] for goal in snapshot["goals"]] == [
        str(goal.pk) for goal in (race, threshold, general)
    ]
    assert snapshot["goals"][0] == {
        "id": str(race.pk),
        "kind": "race",
        "title": "Race",
        "priority": "main",
        "target_date": "2026-11-16",
        "discipline": "running",
        "distance_m": 10_000,
        "target_time_seconds": 2400,
        "metric": "",
        "target_value": None,
    }
    assert snapshot["goals"][1]["metric"] == "ftp"
    assert snapshot["goals"][1]["target_value"] == 300
    assert snapshot["goals"][2]["target_date"] is None
    assert json.loads(json.dumps(snapshot)) == snapshot
    text = json.dumps(snapshot)
    for excluded in ("Private notes", "notes", "created_at", "updated_at", "owner"):
        assert excluded not in text


def test_saving_only_notes_and_timestamps_leaves_the_snapshot_unchanged(alice: User) -> None:
    goal = Goal.objects.create(owner=alice, kind="general", title="Keep training")
    best = BestTime.objects.create(owner=alice, distance="5k", seconds=1200, date=DAY)
    before = collect_inputs(alice)

    goal.notes = "Changed private notes"
    goal.save()
    best.save()

    assert collect_inputs(alice) == before
    assert collect_inputs(alice) == before


def test_ftp_uses_the_existing_source_priority_and_only_the_effective_number(alice: User) -> None:
    estimate = ThresholdValue.objects.create(
        owner=alice, sport="ride", metric="ftp", source="estimated", value=220
    )
    assert collect_inputs(alice)["ftp"] == 220
    intervals = ThresholdValue.objects.create(
        owner=alice, sport="ride", metric="ftp", source="intervals", value=250
    )
    assert collect_inputs(alice)["ftp"] == 250
    manual = ThresholdValue.objects.create(
        owner=alice, sport="ride", metric="ftp", source="manual", value=270
    )
    before = collect_inputs(alice)
    assert before["ftp"] == 270

    estimate.value = 280
    estimate.save()
    manual.basis = "Changed basis"
    manual.save()
    assert collect_inputs(alice) == before

    manual.delete()
    assert collect_inputs(alice)["ftp"] == 250
    intervals.delete()
    assert collect_inputs(alice)["ftp"] == 280


def test_best_times_keep_distance_seconds_and_race_day_in_a_fixed_order(alice: User) -> None:
    BestTime.objects.create(owner=alice, distance="marathon", seconds=12600, date=DAY)
    BestTime.objects.create(owner=alice, distance="5k", seconds=1200, date=date(2020, 1, 1))
    BestTime.objects.create(owner=alice, distance="10k", seconds=2500, date=DAY)
    AvailabilitySettings.objects.create(owner=alice, typical_weekly_minutes=360)

    snapshot = collect_inputs(alice)

    assert snapshot["best_times"] == [
        {"distance": "10k", "seconds": 2500, "date": "2026-11-16"},
        {"distance": "5k", "seconds": 1200, "date": "2020-01-01"},
        {"distance": "marathon", "seconds": 12600, "date": "2026-11-16"},
    ]
    assert snapshot["typical_weekly_minutes"] == 360


@pytest.mark.parametrize("typical", [None, 0, 360])
def test_typical_minutes_are_not_replaced_by_the_weekly_budget(
    alice: User, typical: int | None
) -> None:
    AvailabilitySettings.objects.create(
        owner=alice, typical_weekly_minutes=typical, weekly_budget_minutes=600
    )

    assert collect_inputs(alice)["typical_weekly_minutes"] == typical


def test_every_input_is_scoped_to_the_user(alice: User) -> None:
    before = collect_inputs(alice)
    bob = User.objects.create_user("bob@example.com")
    Goal.objects.create(owner=bob, kind="general", title="Other goal")
    ThresholdValue.objects.create(owner=bob, sport="ride", metric="ftp", source="manual", value=300)
    BestTime.objects.create(owner=bob, distance="5k", seconds=1200, date=DAY)
    AvailabilitySettings.objects.create(owner=bob, typical_weekly_minutes=600)

    assert collect_inputs(alice) == before
    assert collect_inputs(bob)["ftp"] == 300
    assert collect_inputs(bob)["typical_weekly_minutes"] == 600
