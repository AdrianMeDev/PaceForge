from datetime import UTC, date, datetime
from http import HTTPStatus
from typing import Any

import pytest

from accounts.models import User
from activities.load import (
    RPE_LOAD_PER_HOUR,
    done_load_for_week,
    load_of,
    load_source_of,
    rpe_load,
)
from activities.models import Activity
from athletes.models import AthleteProfile

from .conftest import make_user, signed_in

pytestmark = pytest.mark.django_db

START = datetime(2026, 11, 12, 6, 30, tzinfo=UTC)
MONDAY = date(2026, 11, 9)


class TestRpeLoad:
    def test_scale_constant(self) -> None:
        assert RPE_LOAD_PER_HOUR == 10

    @pytest.mark.parametrize(
        ("seconds", "rpe", "load"),
        [
            (3600, 5, 50),  # 1 h × 5 × 10 = 50
            (2700, 7, 53),  # 0.75 h × 7 × 10 = 52.5 -> rounds half up
            (1800, 6, 30),  # 0.5 h × 6 × 10 = 30
            (60, 1, 0),  # 1/60 h × 1 × 10 = 0.166... -> 0
            (5400, 10, 150),  # 1.5 h × 10 × 10 = 150
            (900, 1, 3),  # 0.25 h × 1 × 10 = 2.5 -> rounds half up
            (180, 1, 1),  # 0.05 h × 1 × 10 = 0.5 -> rounds half up
            (179, 1, 0),  # 0.497... -> 0
            (0, 8, 0),
        ],
    )
    def test_it_is_hours_times_rpe_times_scale_rounded_half_up(
        self, seconds: float, rpe: int, load: int
    ) -> None:
        assert rpe_load(seconds, rpe) == load

    @pytest.mark.parametrize(("seconds", "rpe"), [(None, 5), (3600, None), (None, None)])
    def test_without_the_duration_or_the_rpe_there_is_no_load(
        self, seconds: float | None, rpe: int | None
    ) -> None:
        assert rpe_load(seconds, rpe) is None


class TestLoadOfAnActivity:
    def activity(self, **fields: Any) -> Activity:
        defaults: dict[str, Any] = {
            "source": Activity.Source.MANUAL,
            "sport": Activity.Sport.STRENGTH,
            "start_time": START,
        }
        defaults.update(fields)
        return Activity(**defaults)

    def test_intervals_training_load_takes_precedence_over_rpe(self) -> None:
        activity = self.activity(
            source=Activity.Source.INTERVALS_ICU,
            external_id="i123",
            timer_seconds=3600,
            rpe=5,
            training_load=78.0,
        )

        assert load_of(activity) == 78
        assert load_source_of(activity) == "intervals"

    @pytest.mark.parametrize(
        ("training_load", "expected"),
        [(65.25, 65), (65.5, 66), (65.49, 65), (0.0, 0)],
    )
    def test_intervals_training_load_is_rounded_half_up(
        self, training_load: float, expected: int
    ) -> None:
        activity = self.activity(training_load=training_load)

        assert load_of(activity) == expected
        assert load_source_of(activity) == "intervals"

    def test_the_timer_time_counts_for_rpe_fallback(self) -> None:
        activity = self.activity(timer_seconds=3600, elapsed_seconds=7200, rpe=5)

        assert load_of(activity) == 50
        assert load_source_of(activity) == "rpe"

    def test_the_elapsed_time_stands_in_for_the_timer_time(self) -> None:
        activity = self.activity(elapsed_seconds=1800, rpe=6)

        assert load_of(activity) == 30
        assert load_source_of(activity) == "rpe"

    def test_no_training_load_and_no_rpe_means_no_load(self) -> None:
        activity = self.activity(timer_seconds=3600)

        assert load_of(activity) is None
        assert load_source_of(activity) is None

    def test_no_training_load_and_no_duration_means_no_load(self) -> None:
        activity = self.activity(rpe=5)

        assert load_of(activity) is None
        assert load_source_of(activity) is None


class TestDoneLoadForWeek:
    def test_sums_intervals_and_rpe_activities_for_the_user_in_local_week(self) -> None:
        alice: User = make_user("alice@example.com")
        bob: User = make_user("bob@example.com")
        AthleteProfile.objects.create(owner=alice, timezone="Europe/Berlin")

        # 23:30 UTC on Sunday Nov 8 is 00:30 Monday Nov 9 in Berlin -> in week.
        Activity.objects.create(
            owner=alice,
            source=Activity.Source.INTERVALS_ICU,
            external_id="i1",
            sport=Activity.Sport.RUNNING,
            start_time=datetime(2026, 11, 8, 23, 30, tzinfo=UTC),
            training_load=72.6,
        )
        # RPE fallback: 45 min at RPE 7 -> 53.
        Activity.objects.create(
            owner=alice,
            source=Activity.Source.MANUAL,
            sport=Activity.Sport.STRENGTH,
            start_time=datetime(2026, 11, 12, 18, 0, tzinfo=UTC),
            timer_seconds=2700,
            rpe=7,
        )
        # Activity without load -> ignored.
        Activity.objects.create(
            owner=alice,
            source=Activity.Source.MANUAL,
            sport=Activity.Sport.CYCLING,
            start_time=datetime(2026, 11, 13, 18, 0, tzinfo=UTC),
            timer_seconds=3600,
        )
        # 23:30 UTC on Sunday Nov 15 is 00:30 Monday Nov 16 in Berlin -> next week.
        Activity.objects.create(
            owner=alice,
            source=Activity.Source.INTERVALS_ICU,
            external_id="i2",
            sport=Activity.Sport.RUNNING,
            start_time=datetime(2026, 11, 15, 23, 30, tzinfo=UTC),
            training_load=100.0,
        )
        # Another user's activity -> isolated.
        Activity.objects.create(
            owner=bob,
            source=Activity.Source.INTERVALS_ICU,
            external_id="i3",
            sport=Activity.Sport.RUNNING,
            start_time=datetime(2026, 11, 10, 10, 0, tzinfo=UTC),
            training_load=200.0,
        )

        assert done_load_for_week(alice, MONDAY) == 73 + 53

    def test_empty_week_returns_zero(self) -> None:
        alice: User = make_user("alice@example.com")

        assert done_load_for_week(alice, MONDAY) == 0

    def test_requires_a_monday(self) -> None:
        alice: User = make_user("alice@example.com")

        with pytest.raises(ValueError, match="Monday"):
            done_load_for_week(alice, date(2026, 11, 10))


class TestInTheApi:
    def test_the_list_and_the_detail_show_rpe_note_load_and_load_source(self) -> None:
        alice: User = make_user("alice@example.com")
        manual = Activity.objects.create(
            owner=alice,
            source=Activity.Source.MANUAL,
            sport=Activity.Sport.STRENGTH,
            start_time=START,
            timer_seconds=2700,
            rpe=7,
            notes="Legs were heavy",
        )
        intervals = Activity.objects.create(
            owner=alice,
            source=Activity.Source.INTERVALS_ICU,
            external_id="i99",
            sport=Activity.Sport.RUNNING,
            start_time=datetime(2026, 11, 13, 6, 30, tzinfo=UTC),
            timer_seconds=3600,
            training_load=74.6,
            rpe=5,
        )
        api = signed_in(alice)

        results = api.call("GET", "/api/activities/").json()["results"]
        by_id = {item["id"]: item for item in results}

        listed_manual = by_id[str(manual.pk)]
        assert (
            listed_manual["rpe"],
            listed_manual["notes"],
            listed_manual["load"],
            listed_manual["load_source"],
        ) == (7, "Legs were heavy", 53, "rpe")

        listed_intervals = by_id[str(intervals.pk)]
        assert (listed_intervals["load"], listed_intervals["load_source"]) == (75, "intervals")

        detail_manual = api.call("GET", f"/api/activities/{manual.pk}/")
        assert detail_manual.status_code == HTTPStatus.OK
        assert (detail_manual.json()["load"], detail_manual.json()["load_source"]) == (53, "rpe")

        detail_intervals = api.call("GET", f"/api/activities/{intervals.pk}/")
        assert detail_intervals.status_code == HTTPStatus.OK
        assert (detail_intervals.json()["load"], detail_intervals.json()["load_source"]) == (
            75,
            "intervals",
        )

    def test_an_activity_without_training_load_or_rpe_shows_none(self) -> None:
        alice: User = make_user("alice@example.com")
        Activity.objects.create(
            owner=alice,
            source=Activity.Source.MANUAL,
            sport=Activity.Sport.RUNNING,
            start_time=START,
            timer_seconds=3600,
        )

        listed = signed_in(alice).call("GET", "/api/activities/").json()["results"][0]

        assert (listed["rpe"], listed["notes"], listed["load"], listed["load_source"]) == (
            None,
            "",
            None,
            None,
        )
