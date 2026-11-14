from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from accounts.models import User
from activities.duplicates import (
    DURATION_TOLERANCE_PERCENT,
    START_TOLERANCE,
    duration_of,
    find_duplicate,
    similar_durations,
)
from activities.models import Activity

pytestmark = pytest.mark.django_db

START = datetime(2026, 11, 12, 6, 30, tzinfo=UTC)
HOUR = 3600.0


@pytest.fixture
def alice() -> User:
    return User.objects.create_user("alice@example.com")


@pytest.fixture
def bob() -> User:
    return User.objects.create_user("bob@example.com")


def make(owner: User, **fields: Any) -> Activity:
    values: dict[str, Any] = {
        "source": Activity.Source.MANUAL,
        "sport": Activity.Sport.RUNNING,
        "start_time": START,
        "timer_seconds": HOUR,
        **fields,
    }
    return Activity.objects.create(owner=owner, **values)


class TestDuration:
    def test_the_timer_time_counts_and_the_elapsed_time_stands_in(self) -> None:
        assert duration_of(100, 200) == 100
        assert duration_of(None, 200) == 200
        assert duration_of(None, None) is None
        assert duration_of(0, 200) == 0

    @pytest.mark.parametrize(
        ("first", "second", "same"),
        [
            (1000, 1000, True),
            (900, 1000, True),  # exactly 10 % of the longer one
            (1000, 900, True),
            (1000, 1112, False),  # a hair above
            (1000, 1100, True),
            (1000, 2000, False),
            (None, 1000, True),
            (1000, None, True),
            (None, None, True),
            (0, 0, True),
        ],
    )
    def test_a_tenth_of_the_longer_one_is_the_most_they_may_differ(
        self, first: float | None, second: float | None, same: bool
    ) -> None:
        assert similar_durations(first, second) is same

    def test_the_tolerances_are_those_of_the_documentation(self) -> None:
        assert START_TOLERANCE == timedelta(minutes=10)
        assert DURATION_TOLERANCE_PERCENT == 10


class TestFinding:
    def test_the_same_start_and_sport_is_always_the_same_session(self, alice: User) -> None:
        found = make(alice)

        # Even with a very different duration: the database would not take both.
        assert find_duplicate(alice, "running", START, 10 * HOUR) == found

    def test_a_start_ten_minutes_apart_with_the_same_duration_matches(self, alice: User) -> None:
        found = make(alice)

        assert find_duplicate(alice, "running", START + START_TOLERANCE, HOUR) == found
        assert find_duplicate(alice, "running", START - START_TOLERANCE, HOUR) == found

    def test_a_start_a_second_over_the_tolerance_does_not(self, alice: User) -> None:
        make(alice)
        late = START + START_TOLERANCE + timedelta(seconds=1)
        early = START - START_TOLERANCE - timedelta(seconds=1)

        assert find_duplicate(alice, "running", late, HOUR) is None
        assert find_duplicate(alice, "running", early, HOUR) is None

    def test_a_near_start_with_another_duration_is_another_session(self, alice: User) -> None:
        make(alice)

        assert find_duplicate(alice, "running", START + timedelta(minutes=5), HOUR / 2) is None

    def test_a_near_start_without_a_duration_on_either_side_matches(self, alice: User) -> None:
        found = make(alice, timer_seconds=None, elapsed_seconds=None)

        assert find_duplicate(alice, "running", START + timedelta(minutes=5), HOUR) == found
        make(alice, start_time=START + timedelta(hours=5))
        assert find_duplicate(alice, "running", START + timedelta(hours=5, minutes=2), None)

    def test_the_elapsed_time_stands_in_for_a_missing_timer_time(self, alice: User) -> None:
        make(alice, timer_seconds=None, elapsed_seconds=HOUR)

        near = START + timedelta(minutes=3)
        assert find_duplicate(alice, "running", near, HOUR) is not None
        assert find_duplicate(alice, "running", near, HOUR * 3) is None

    def test_another_sport_never_matches(self, alice: User) -> None:
        make(alice)

        assert find_duplicate(alice, "cycling", START, HOUR) is None
        assert find_duplicate(alice, "cycling", START + timedelta(minutes=2), HOUR) is None

    def test_another_users_activity_never_matches(self, alice: User, bob: User) -> None:
        make(bob)

        assert find_duplicate(alice, "running", START, HOUR) is None

    def test_where_several_match_the_closest_start_wins(self, alice: User) -> None:
        make(alice, start_time=START - timedelta(minutes=8))
        closest = make(alice, start_time=START + timedelta(minutes=2))
        make(alice, start_time=START + timedelta(minutes=9))

        assert find_duplicate(alice, "running", START, HOUR) == closest

    def test_nothing_at_all_is_none(self, alice: User) -> None:
        assert find_duplicate(alice, "running", START, HOUR) is None

    def test_it_makes_one_query_however_many_activities_there_are(self, alice: User) -> None:
        for number in range(5):
            make(alice, start_time=START + timedelta(minutes=number))

        with CaptureQueriesContext(connection) as queries:
            find_duplicate(alice, "running", START, HOUR)

        assert len(queries) == 1
