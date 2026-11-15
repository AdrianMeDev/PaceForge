import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from accounts.models import User
from availability.models import SportPreference
from availability.preferences import sport_preferences

pytestmark = pytest.mark.django_db


@pytest.fixture
def alice() -> User:
    return User.objects.create_user("alice@example.com")


@pytest.fixture
def bob() -> User:
    return User.objects.create_user("bob@example.com")


def test_a_user_who_said_nothing_has_nothing(alice: User) -> None:
    assert sport_preferences(alice) == []


def test_the_sports_come_in_the_order_of_the_sports_with_what_was_said(alice: User) -> None:
    SportPreference.objects.create(owner=alice, sport="strength", role="supplementary")
    SportPreference.objects.create(
        owner=alice, sport="running", role="goal", sessions_min=3, sessions_max=5
    )

    assert sport_preferences(alice) == [
        ("running", "goal", 3, 5),
        ("strength", "supplementary", None, None),
    ]


def test_an_empty_row_says_nothing(alice: User) -> None:
    SportPreference.objects.create(owner=alice, sport="swimming")

    assert sport_preferences(alice) == []


def test_a_zero_is_something_said(alice: User) -> None:
    SportPreference.objects.create(owner=alice, sport="swimming", sessions_max=0)

    assert sport_preferences(alice) == [("swimming", None, None, 0)]


def test_the_rows_of_another_user_are_not_there(alice: User, bob: User) -> None:
    SportPreference.objects.create(owner=bob, sport="running", role="goal")

    assert sport_preferences(alice) == []


def test_it_takes_one_query(alice: User) -> None:
    for sport in ("running", "cycling", "swimming", "strength"):
        SportPreference.objects.create(owner=alice, sport=sport, role="goal")

    with CaptureQueriesContext(connection) as queries:
        sport_preferences(alice)

    assert len(queries) == 1
