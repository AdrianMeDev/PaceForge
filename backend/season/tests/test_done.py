from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from accounts.models import User
from activities.models import Activity
from athletes.models import AthleteProfile
from season.done import done_minutes, done_week_totals

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


class TestDoneWeekTotals:
    def test_load_prefers_intervals_then_rpe_and_unknown_load_adds_zero(self, alice: User) -> None:
        activity(alice, "2027-07-13T08:00", 3600, 1, training_load=80.5, rpe=10)
        activity(alice, "2027-07-13T18:00", 1800, 2, rpe=6)
        activity(alice, "2027-07-14T08:00", None, 3, elapsed=1800, rpe=4, sport="cycling")
        activity(alice, "2027-07-15T08:00", 600, 4, sport="other")

        assert done_week_totals(alice, [MONDAY]) == {
            MONDAY: {
                "minutes": [("running", 90), ("cycling", 30), ("other", 10)],
                "load": [("running", 111), ("cycling", 20)],
            }
        }

    def test_load_without_duration_still_counts_and_zero_intervals_load_wins(
        self, alice: User
    ) -> None:
        activity(alice, "2027-07-13T08:00", None, 1, training_load=25)
        activity(alice, "2027-07-14T08:00", 3600, 2, rpe=10, training_load=0, sport="cycling")

        assert done_week_totals(alice, [MONDAY])[MONDAY] == {
            "minutes": [("cycling", 60)],
            "load": [("running", 25)],
        }

    def test_minutes_round_after_summing_but_load_rounds_per_activity(self, alice: User) -> None:
        activity(alice, "2027-07-13T08:00", 29, 1, training_load=0.5)
        activity(alice, "2027-07-13T09:00", 29, 2, training_load=0.5)

        assert done_week_totals(alice, [MONDAY])[MONDAY] == {
            "minutes": [("running", 1)],
            "load": [("running", 2)],
        }

    def test_empty_weeks_and_duplicate_mondays(self, alice: User) -> None:
        assert done_week_totals(alice, [MONDAY, MONDAY]) == {MONDAY: {"minutes": [], "load": []}}
        with CaptureQueriesContext(connection) as queries:
            assert done_week_totals(alice, []) == {}
        assert len(queries) == 0

    def test_local_week_boundaries_and_gaps_match_done_minutes(self, alice: User) -> None:
        AthleteProfile.objects.create(owner=alice, timezone="Asia/Tokyo")
        activity(alice, "2027-07-11T14:59", 3600, 1, training_load=10)  # before the first week
        activity(alice, "2027-07-11T15:00", 1800, 2, training_load=20)  # local Monday
        activity(alice, "2027-07-18T14:59", 29, 3, training_load=30)  # local Sunday
        activity(alice, "2027-07-18T15:00", 3600, 4, training_load=40)  # unrequested week
        activity(alice, "2027-08-01T15:00", 3600, 5, training_load=50)  # after the last week
        weeks = [MONDAY + timedelta(weeks=2), MONDAY]

        found = done_week_totals(alice, weeks)

        assert {monday: totals["minutes"] for monday, totals in found.items()} == done_minutes(
            alice, weeks
        )
        assert found == {
            MONDAY: {"minutes": [("running", 30)], "load": [("running", 50)]},
            MONDAY + timedelta(weeks=2): {"minutes": [], "load": []},
        }

    def test_other_users_minutes_load_and_timezone_do_not_count(
        self, alice: User, bob: User
    ) -> None:
        AthleteProfile.objects.create(owner=bob, timezone="Asia/Tokyo")
        activity(bob, "2027-07-13T08:00", 3600, 1, training_load=100)
        activity(alice, "2027-07-18T16:00", 3600, 2, rpe=6)

        assert done_week_totals(alice, [MONDAY])[MONDAY] == {
            "minutes": [("running", 60)],
            "load": [("running", 60)],
        }

    @pytest.mark.parametrize("count", [1, 52])
    def test_two_queries_regardless_of_the_week_count(self, alice: User, count: int) -> None:
        activity(alice, "2027-07-13T08:00", 3600, 1, rpe=6)
        weeks = [MONDAY + timedelta(weeks=n) for n in range(count)]

        with CaptureQueriesContext(connection) as queries:
            found = done_week_totals(alice, weeks)

        assert len(queries) == 2
        assert len(found) == count
        assert found[MONDAY]["load"] == [("running", 60)]
