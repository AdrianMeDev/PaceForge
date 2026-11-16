from datetime import UTC, date, datetime, timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from accounts.models import User
from athletes import best_times
from athletes.best_times import (
    PACE_MAX,
    PACE_MIN,
    WINDOW_DAYS,
    Entry,
    basis_of,
    counting,
    entries,
    pace_of,
)
from athletes.models import BestTime, ThresholdValue
from athletes.thresholds import all_candidates, candidates, effective
from athletes.vdot import DISTANCES, VDOT_MAX, VDOT_MIN, vdot

pytestmark = pytest.mark.django_db

TODAY = date(2026, 11, 16)


@pytest.fixture(autouse=True)
def _fixed_day(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(best_times, "_today", lambda: TODAY)


@pytest.fixture
def alice() -> User:
    return User.objects.create_user("alice@example.com")


@pytest.fixture
def bob() -> User:
    return User.objects.create_user("bob@example.com")


def race(owner: User, distance: str, time: str, days_ago: int) -> BestTime:
    """A best time such as ``19:57`` that was run ``days_ago`` days before the fixed day."""
    seconds = 0
    for part in time.split(":"):
        seconds = seconds * 60 + int(part)
    return BestTime.objects.create(
        owner=owner, distance=distance, seconds=seconds, date=TODAY - timedelta(days=days_ago)
    )


class TestTheEntries:
    def test_without_times_there_are_none(self, alice: User) -> None:
        assert entries(alice) == []

    def test_they_come_in_the_order_of_the_distances_with_their_vdot(self, alice: User) -> None:
        race(alice, "marathon", "3:10:49", 40)
        race(alice, "5k", "19:57", 10)

        found = entries(alice)

        assert [entry.distance for entry in found] == ["5k", "marathon"]
        assert found[0].vdot == pytest.approx(50, abs=0.1)
        assert found[0].vdot == vdot(DISTANCES["5k"], found[0].seconds)

    def test_a_race_inside_the_window_is_recent_and_an_older_one_is_not(self, alice: User) -> None:
        race(alice, "5k", "20:00", WINDOW_DAYS)
        race(alice, "10k", "42:00", WINDOW_DAYS + 1)

        recent = {entry.distance: entry.recent for entry in entries(alice)}

        assert recent == {"5k": True, "10k": False}

    def test_a_time_the_database_holds_but_nobody_can_run_is_left_out(self, alice: User) -> None:
        race(alice, "5k", "5:00", 10)  # a VDOT far above anything a runner has

        assert entries(alice) == []

    def test_it_takes_one_query_and_shows_only_the_own_times(self, alice: User, bob: User) -> None:
        race(alice, "5k", "20:00", 10)
        race(bob, "10k", "45:00", 10)

        with CaptureQueriesContext(connection) as queries:
            found = entries(alice)

        assert [entry.distance for entry in found] == ["5k"]
        assert len(queries) == 1


class TestWhichOneCounts:
    def test_without_a_recent_time_none_counts(self, alice: User) -> None:
        race(alice, "5k", "20:00", WINDOW_DAYS + 30)

        assert counting(entries(alice)) is None

    def test_the_newest_race_counts_even_if_an_older_one_is_better(self, alice: User) -> None:
        race(alice, "5k", "19:00", 200)
        race(alice, "10k", "45:00", 20)

        found = counting(entries(alice))

        assert found is not None
        assert found.distance == "10k"

    def test_on_the_same_day_the_higher_vdot_counts(self, alice: User) -> None:
        race(alice, "5k", "22:00", 20)
        race(alice, "10k", "42:00", 20)
        race(alice, "marathon", "4:30:00", 20)
        found = entries(alice)

        counted = counting(found)

        assert counted is not None
        assert counted.vdot == max(entry.vdot for entry in found)
        assert counted.distance == "10k"

    def test_a_recent_time_counts_over_a_better_old_one(self, alice: User) -> None:
        race(alice, "5k", "17:00", WINDOW_DAYS + 5)
        race(alice, "10k", "50:00", 300)

        found = counting(entries(alice))

        assert found is not None
        assert found.distance == "10k"


class TestThePace:
    def test_it_is_the_threshold_pace_of_the_vdot_in_whole_seconds(self, alice: User) -> None:
        race(alice, "5k", "19:57", 10)
        (entry,) = entries(alice)

        pace = pace_of(entry)

        assert pace is not None
        assert pace == round(pace)
        assert divmod(round(pace), 60) == (4, 15)

    def test_it_stays_inside_what_a_threshold_can_be_for_every_possible_vdot(self) -> None:
        for number in range(int(VDOT_MIN), int(VDOT_MAX) + 1):
            entry = Entry("5k", 1200, TODAY, float(number), True, datetime.now(UTC))
            pace = pace_of(entry)
            assert pace is not None
            assert PACE_MIN <= pace <= PACE_MAX

    def test_the_basis_names_the_vdot_the_distance_and_the_day_and_nothing_else(
        self, alice: User
    ) -> None:
        race(alice, "half_marathon", "1:35:00", 12)
        (entry,) = entries(alice)

        assert basis_of(entry) == (
            f"VDOT {entry.vdot:.1f} from your Half marathon on {TODAY - timedelta(days=12)}"
        )


class TestAsAThreshold:
    def test_a_recent_time_is_a_candidate_for_the_running_pace(self, alice: User) -> None:
        race(alice, "5k", "19:57", 10)

        (found,) = candidates(alice, "run", "threshold_pace")

        assert found.source == "best_time"
        assert divmod(round(found.value), 60) == (4, 15)
        assert found.basis.startswith("VDOT 50.0 from your 5 km on ")

    def test_it_is_no_candidate_for_any_other_threshold(self, alice: User) -> None:
        race(alice, "5k", "19:57", 10)

        assert candidates(alice, "ride", "ftp") == []
        assert candidates(alice, "run", "lthr") == []
        assert candidates(alice, "run", "max_hr") == []

    def test_an_old_time_is_no_candidate(self, alice: User) -> None:
        race(alice, "5k", "19:57", WINDOW_DAYS + 1)

        assert candidates(alice, "run", "threshold_pace") == []
        assert all_candidates(alice) == {}

    def test_a_typed_value_counts_before_it_and_every_other_source_after(self, alice: User) -> None:
        race(alice, "5k", "19:57", 10)
        for source, value in (("manual", 280), ("intervals", 262), ("estimated", 241)):
            ThresholdValue.objects.create(
                owner=alice, sport="run", metric="threshold_pace", source=source, value=value
            )

        found = candidates(alice, "run", "threshold_pace")

        assert [candidate.source for candidate in found] == [
            "manual",
            "best_time",
            "intervals",
            "estimated",
        ]
        assert effective(alice, "run", "threshold_pace") == found[0]

    def test_without_a_typed_value_it_counts_before_intervals_and_the_estimate(
        self, alice: User
    ) -> None:
        race(alice, "5k", "19:57", 10)
        for source, value in (("intervals", 262), ("estimated", 241)):
            ThresholdValue.objects.create(
                owner=alice, sport="run", metric="threshold_pace", source=source, value=value
            )

        found = effective(alice, "run", "threshold_pace")

        assert found is not None
        assert found.source == "best_time"

    def test_all_candidates_has_it_next_to_the_stored_ones_in_two_queries(
        self, alice: User
    ) -> None:
        race(alice, "10k", "41:21", 10)
        ThresholdValue.objects.create(
            owner=alice, sport="ride", metric="ftp", source="manual", value=250
        )

        with CaptureQueriesContext(connection) as queries:
            found = all_candidates(alice)

        assert set(found) == {("ride", "ftp"), ("run", "threshold_pace")}
        assert [c.source for c in found[("run", "threshold_pace")]] == ["best_time"]
        assert len(queries) == 2

    def test_the_time_of_another_user_is_not_a_candidate(self, alice: User, bob: User) -> None:
        race(bob, "5k", "19:57", 10)

        assert candidates(alice, "run", "threshold_pace") == []

    def test_a_changed_time_changes_the_pace(self, alice: User) -> None:
        stored = race(alice, "5k", "25:00", 10)
        slow = effective(alice, "run", "threshold_pace")

        stored.seconds = 20 * 60
        stored.save()
        fast = effective(alice, "run", "threshold_pace")

        assert slow is not None and fast is not None
        assert fast.value < slow.value

    def test_reading_writes_nothing(self, alice: User) -> None:
        race(alice, "5k", "19:57", 10)

        candidates(alice, "run", "threshold_pace")
        all_candidates(alice)

        assert not ThresholdValue.objects.exists()
