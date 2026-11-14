from datetime import UTC, datetime
from http import HTTPStatus
from typing import Any

import pytest

from accounts.models import User
from activities.load import load_of, session_load
from activities.models import Activity

from .conftest import make_user, signed_in

pytestmark = pytest.mark.django_db

START = datetime(2026, 11, 12, 6, 30, tzinfo=UTC)


class TestSessionLoad:
    @pytest.mark.parametrize(
        ("seconds", "rpe", "load"),
        [
            (3600, 5, 300),  # an hour at 5
            (2700, 7, 315),  # 45 minutes at 7
            (60, 1, 1),
            (5400, 10, 900),
            (90, 3, 5),  # 4.5 rounds up
            (30, 1, 1),  # 0.5 rounds up
            (29, 1, 0),
            (0, 8, 0),
        ],
    )
    def test_it_is_minutes_times_rpe_rounded_half_up(
        self, seconds: float, rpe: int, load: int
    ) -> None:
        assert session_load(seconds, rpe) == load

    @pytest.mark.parametrize(("seconds", "rpe"), [(None, 5), (3600, None), (None, None)])
    def test_without_the_duration_or_the_rpe_there_is_no_load(
        self, seconds: float | None, rpe: int | None
    ) -> None:
        assert session_load(seconds, rpe) is None


class TestLoadOfAnActivity:
    def activity(self, **fields: Any) -> Activity:
        return Activity(
            source=Activity.Source.MANUAL,
            sport=Activity.Sport.STRENGTH,
            start_time=START,
            **fields,
        )

    def test_the_timer_time_counts(self) -> None:
        assert load_of(self.activity(timer_seconds=3600, elapsed_seconds=7200, rpe=5)) == 300

    def test_the_elapsed_time_stands_in_for_the_timer_time(self) -> None:
        assert load_of(self.activity(elapsed_seconds=1800, rpe=6)) == 180

    def test_no_rpe_no_load(self) -> None:
        assert load_of(self.activity(timer_seconds=3600)) is None

    def test_no_duration_no_load(self) -> None:
        assert load_of(self.activity(rpe=5)) is None


class TestInTheApi:
    def test_the_list_and_the_detail_show_rpe_note_and_load(self) -> None:
        alice: User = make_user("alice@example.com")
        found = Activity.objects.create(
            owner=alice,
            source=Activity.Source.MANUAL,
            sport=Activity.Sport.STRENGTH,
            start_time=START,
            timer_seconds=2700,
            rpe=7,
            notes="Legs were heavy",
        )
        api = signed_in(alice)

        listed = api.call("GET", "/api/activities/").json()["results"][0]
        detail = api.call("GET", f"/api/activities/{found.pk}/")

        assert (listed["rpe"], listed["notes"], listed["load"]) == (7, "Legs were heavy", 315)
        assert detail.status_code == HTTPStatus.OK
        assert detail.json()["load"] == 315

    def test_an_activity_without_an_rpe_shows_nothing_of_the_kind(self) -> None:
        alice: User = make_user("alice@example.com")
        Activity.objects.create(
            owner=alice,
            source=Activity.Source.MANUAL,
            sport=Activity.Sport.RUNNING,
            start_time=START,
            timer_seconds=3600,
        )

        listed = signed_in(alice).call("GET", "/api/activities/").json()["results"][0]

        assert (listed["rpe"], listed["notes"], listed["load"]) == (None, "", None)
