from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from accounts.models import User
from activities.models import Activity
from athletes.models import AthleteProfile
from season.done import done_minutes

pytestmark = pytest.mark.django_db

MONDAY = date(2027, 7, 12)


@pytest.fixture
def alice() -> User:
    return User.objects.create_user("alice@example.com")


@pytest.fixture
def bob() -> User:
    return User.objects.create_user("bob@example.com")


def at(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


def activity(owner: User, start: str, timer: float | None = 3600, n: int = 0, **f: Any) -> None:
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


class TestTheMinutesDone:
    def test_a_week_without_activities_is_an_empty_list(self, alice: User) -> None:
        assert done_minutes(alice, [MONDAY]) == {MONDAY: []}

    def test_no_weeks_are_no_answer(self, alice: User) -> None:
        assert done_minutes(alice, []) == {}

    def test_the_minutes_of_a_sport_are_added_up_in_the_order_of_the_chart(
        self, alice: User
    ) -> None:
        activity(alice, "2027-07-13T08:00", 1800, 1, sport="cycling")
        activity(alice, "2027-07-13T18:00", 1800, 2, sport="cycling")
        activity(alice, "2027-07-14T08:00", 3600, 3, sport="running")
        activity(alice, "2027-07-15T08:00", 600, 4, sport="other")

        assert done_minutes(alice, [MONDAY]) == {
            MONDAY: [("running", 60), ("cycling", 60), ("other", 10)]
        }

    def test_each_week_has_its_own_minutes(self, alice: User) -> None:
        activity(alice, "2027-07-14T08:00", 3600, 1)
        activity(alice, "2027-07-21T08:00", 1800, 2)

        found = done_minutes(
            alice, [MONDAY + timedelta(weeks=1), MONDAY, MONDAY + timedelta(weeks=2)]
        )

        assert found == {
            MONDAY: [("running", 60)],
            MONDAY + timedelta(weeks=1): [("running", 30)],
            MONDAY + timedelta(weeks=2): [],
        }

    def test_the_week_is_monday_to_sunday(self, alice: User) -> None:
        activity(alice, "2027-07-18T23:00", 3600, 1)  # Sunday evening: this week
        activity(alice, "2027-07-19T00:00", 1200, 2)  # Monday morning: the next

        found = done_minutes(alice, [MONDAY, MONDAY + timedelta(weeks=1)])

        assert found[MONDAY] == [("running", 60)]
        assert found[MONDAY + timedelta(weeks=1)] == [("running", 20)]

    def test_the_week_is_cut_in_the_time_zone_of_the_athlete(self, alice: User) -> None:
        AthleteProfile.objects.create(owner=alice, timezone="Asia/Tokyo")
        # 16:00 UTC on Sunday is 01:00 on Monday in Tokyo
        activity(alice, "2027-07-18T16:00", 3600, 1)

        found = done_minutes(alice, [MONDAY, MONDAY + timedelta(weeks=1)])

        assert found[MONDAY] == []
        assert found[MONDAY + timedelta(weeks=1)] == [("running", 60)]

    def test_the_timer_time_counts_and_the_elapsed_time_stands_in(self, alice: User) -> None:
        activity(alice, "2027-07-13T08:00", 1800, 1, elapsed=7200)
        activity(alice, "2027-07-14T08:00", None, 2, elapsed=1800)

        assert done_minutes(alice, [MONDAY]) == {MONDAY: [("running", 60)]}

    def test_an_activity_without_a_duration_does_not_count(self, alice: User) -> None:
        activity(alice, "2027-07-13T08:00", None, 1)

        assert done_minutes(alice, [MONDAY]) == {MONDAY: []}

    def test_the_seconds_are_added_up_before_they_are_rounded(self, alice: User) -> None:
        for n in range(4):
            activity(alice, f"2027-07-1{3 + n}T08:00", 29, n)  # 4 x 29 s = 116 s

        assert done_minutes(alice, [MONDAY]) == {MONDAY: [("running", 2)]}

    @pytest.mark.parametrize(("seconds", "minutes"), [(29, 0), (30, 1), (89, 1), (90, 2)])
    def test_half_a_minute_rounds_up(self, alice: User, seconds: int, minutes: int) -> None:
        activity(alice, "2027-07-13T08:00", seconds, 1)

        found = done_minutes(alice, [MONDAY])[MONDAY]

        assert found == ([("running", minutes)] if minutes else [])

    def test_activities_outside_the_weeks_asked_for_do_not_count(self, alice: User) -> None:
        activity(alice, "2027-07-11T20:00", 3600, 1)
        activity(alice, "2027-07-19T08:00", 3600, 2)

        assert done_minutes(alice, [MONDAY]) == {MONDAY: []}

    def test_the_activities_of_another_user_never_count(self, alice: User, bob: User) -> None:
        activity(bob, "2027-07-13T08:00", 3600, 1)

        assert done_minutes(alice, [MONDAY]) == {MONDAY: []}

    def test_it_takes_two_queries_however_many_weeks(self, alice: User) -> None:
        for n in range(30):
            activity(alice, f"2027-07-{(n % 17) + 12:02d}T{8 + n // 17:02d}:00", 600, n)
        weeks = [MONDAY + timedelta(weeks=n) for n in range(52)]

        with CaptureQueriesContext(connection) as queries:
            done_minutes(alice, weeks)

        assert len(queries) == 2
