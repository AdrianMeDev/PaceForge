from datetime import date

import pytest
from django.contrib.auth.models import AnonymousUser
from django.db import IntegrityError, transaction

from accounts.models import User
from wellness.models import DailyWellness

pytestmark = pytest.mark.django_db

DAY = date(2027, 7, 19)


@pytest.fixture
def alice() -> User:
    return User.objects.create_user("alice@example.com")


@pytest.fixture
def bob() -> User:
    return User.objects.create_user("bob@example.com")


def make(owner: User, **fields: object) -> DailyWellness:
    return DailyWellness.objects.create(owner=owner, day=DAY, **fields)


class TestConstraints:
    def test_two_rows_for_the_same_user_and_day_are_rejected(self, alice: User) -> None:
        make(alice, sleep_minutes=480)
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                make(alice, sleep_minutes=420)

    def test_two_users_may_have_the_same_day(self, alice: User, bob: User) -> None:
        make(alice, sleep_minutes=480)
        make(bob, sleep_minutes=420)
        assert DailyWellness.objects.count() == 2

    @pytest.mark.parametrize(
        ("field", "low", "high"),
        [
            ("sleep_minutes", 1, 1440),
            ("hrv", 1, 300),
            ("resting_hr", 25, 120),
            ("weight_kg", 25, 300),
        ],
    )
    def test_out_of_range_values_are_rejected(
        self, alice: User, field: str, low: int, high: int
    ) -> None:
        for bad in (low - 1, high + 1):
            with pytest.raises(IntegrityError):
                with transaction.atomic():
                    make(alice, **{field: bad})

    def test_every_metric_may_be_empty_on_a_day(self, alice: User) -> None:
        row = make(alice)
        assert (row.sleep_minutes, row.hrv, row.resting_hr, row.weight_kg) == (
            None,
            None,
            None,
            None,
        )


class TestIsolation:
    def test_for_user_returns_only_the_users_rows(self, alice: User, bob: User) -> None:
        mine = make(alice, sleep_minutes=480)
        make(bob, sleep_minutes=420)

        assert list(DailyWellness.objects.for_user(alice)) == [mine]
        assert not DailyWellness.objects.for_user(bob).filter(pk=mine.pk).exists()

    def test_anonymous_users_own_nothing(self, alice: User) -> None:
        make(alice, sleep_minutes=480)
        assert not DailyWellness.objects.for_user(AnonymousUser()).exists()
