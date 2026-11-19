from datetime import date

import pytest

from accounts.models import User
from integrations.intervals import IntervalsWellness
from wellness.models import DailyWellness
from wellness.sync import store_wellness

pytestmark = pytest.mark.django_db

DAY = date(2027, 7, 19)


@pytest.fixture
def alice() -> User:
    return User.objects.create_user("alice@example.com")


@pytest.fixture
def bob() -> User:
    return User.objects.create_user("bob@example.com")


def entry(
    day: date = DAY,
    *,
    sleep_minutes: int | None = None,
    hrv: float | None = None,
    resting_hr: int | None = None,
    weight_kg: float | None = None,
) -> IntervalsWellness:
    return IntervalsWellness(
        day=day,
        sleep_minutes=sleep_minutes,
        hrv=hrv,
        resting_hr=resting_hr,
        weight_kg=weight_kg,
    )


class TestUpsert:
    def test_new_rows_are_created(self, alice: User) -> None:
        assert store_wellness(alice, [entry(DAY, sleep_minutes=480)]) == 1
        stored = DailyWellness.objects.for_user(alice).get(day=DAY)
        assert stored.sleep_minutes == 480

    def test_an_unchanged_sync_is_idempotent(self, alice: User) -> None:
        first = entry(DAY, sleep_minutes=480, hrv=60.0)
        assert store_wellness(alice, [first]) == 1
        before = DailyWellness.objects.for_user(alice).get(day=DAY).updated_at
        assert store_wellness(alice, [first]) == 0
        after = DailyWellness.objects.for_user(alice).get(day=DAY)
        assert after.updated_at == before
        assert DailyWellness.objects.count() == 1

    def test_a_changed_metric_updates_the_row(self, alice: User) -> None:
        assert store_wellness(alice, [entry(DAY, sleep_minutes=480)]) == 1
        assert store_wellness(alice, [entry(DAY, sleep_minutes=420)]) == 1
        stored = DailyWellness.objects.for_user(alice).get(day=DAY)
        assert stored.sleep_minutes == 420
        assert DailyWellness.objects.count() == 1

    def test_the_count_split_between_creates_and_updates(self, alice: User) -> None:
        store_wellness(alice, [entry(DAY, sleep_minutes=480)])
        changed = store_wellness(
            alice,
            [
                entry(DAY, sleep_minutes=480),  # unchanged
                entry(DAY.replace(day=18), sleep_minutes=420),  # new
                entry(DAY.replace(day=17), sleep_minutes=400),  # new
            ],
        )
        assert changed == 2
        assert DailyWellness.objects.count() == 3

    def test_clearing_a_metric_is_an_update(self, alice: User) -> None:
        store_wellness(alice, [entry(DAY, sleep_minutes=480)])
        assert store_wellness(alice, [entry(DAY)]) == 1
        assert DailyWellness.objects.for_user(alice).get(day=DAY).sleep_minutes is None


class TestIsolation:
    def test_one_users_entries_never_touch_another(self, alice: User, bob: User) -> None:
        store_wellness(alice, [entry(DAY, sleep_minutes=480)])
        store_wellness(bob, [entry(DAY, sleep_minutes=360)])

        assert DailyWellness.objects.for_user(alice).count() == 1
        assert DailyWellness.objects.for_user(bob).count() == 1
        assert DailyWellness.objects.for_user(alice).get(day=DAY).sleep_minutes == 480
        assert DailyWellness.objects.for_user(bob).get(day=DAY).sleep_minutes == 360

    def test_upserting_one_user_does_not_update_the_other(self, alice: User, bob: User) -> None:
        store_wellness(alice, [entry(DAY, sleep_minutes=480)])
        store_wellness(bob, [entry(DAY, sleep_minutes=360)])
        changed = store_wellness(alice, [entry(DAY, sleep_minutes=420)])

        assert changed == 1
        assert DailyWellness.objects.for_user(bob).get(day=DAY).sleep_minutes == 360
