from datetime import date, timedelta

import pytest

from availability.absences import note_illness
from availability.models import UnavailablePeriod
from availability.serializers import MAX_PERIODS

from .conftest import make_user

pytestmark = pytest.mark.django_db

MONDAY = date(2026, 3, 2)


def illness_count(user) -> int:
    return (
        UnavailablePeriod.objects.for_user(user).filter(kind=UnavailablePeriod.Kind.ILLNESS).count()
    )


def test_creates_an_illness_period():
    user = make_user("ill@example.com")

    period = note_illness(user, MONDAY, MONDAY + timedelta(days=2))

    assert period is not None
    assert period.owner == user
    assert period.kind == UnavailablePeriod.Kind.ILLNESS
    assert (period.start_date, period.end_date) == (MONDAY, MONDAY + timedelta(days=2))
    assert illness_count(user) == 1


def test_extends_an_overlapping_period_instead_of_adding_one():
    user = make_user("ill@example.com")
    note_illness(user, MONDAY, MONDAY + timedelta(days=2))

    period = note_illness(user, MONDAY + timedelta(days=1), MONDAY + timedelta(days=4))

    assert period is not None
    assert (period.start_date, period.end_date) == (MONDAY, MONDAY + timedelta(days=4))
    assert illness_count(user) == 1


def test_extends_an_adjacent_period():
    user = make_user("ill@example.com")
    note_illness(user, MONDAY, MONDAY)

    period = note_illness(user, MONDAY + timedelta(days=1), MONDAY + timedelta(days=3))

    assert period is not None
    assert (period.start_date, period.end_date) == (MONDAY, MONDAY + timedelta(days=3))
    assert illness_count(user) == 1


def test_a_gap_leaves_two_periods():
    user = make_user("ill@example.com")
    note_illness(user, MONDAY, MONDAY)

    period = note_illness(user, MONDAY + timedelta(days=2), MONDAY + timedelta(days=3))

    assert period is not None
    assert period.start_date == MONDAY + timedelta(days=2)
    assert illness_count(user) == 2


def test_nothing_is_stored_at_the_limit():
    user = make_user("ill@example.com")
    for number in range(MAX_PERIODS):
        UnavailablePeriod.objects.create(
            owner=user,
            kind=UnavailablePeriod.Kind.OTHER,
            start_date=MONDAY + timedelta(days=3 * number),
            end_date=MONDAY + timedelta(days=3 * number),
        )

    assert note_illness(user, MONDAY + timedelta(days=1), MONDAY + timedelta(days=1)) is None
    assert illness_count(user) == 0


def test_another_users_periods_stay_untouched():
    user = make_user("ill@example.com")
    other = make_user("other@example.com")
    other_period = UnavailablePeriod.objects.create(
        owner=other,
        kind=UnavailablePeriod.Kind.ILLNESS,
        start_date=MONDAY,
        end_date=MONDAY,
    )

    period = note_illness(user, MONDAY, MONDAY + timedelta(days=1))

    assert period is not None
    other_period.refresh_from_db()
    assert (other_period.start_date, other_period.end_date) == (MONDAY, MONDAY)
    assert illness_count(other) == 1
    assert illness_count(user) == 1
