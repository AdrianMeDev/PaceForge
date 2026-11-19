import base64
import json
import os
import subprocess
import sys
from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime, timedelta
from http import HTTPStatus
from pathlib import Path
from typing import Any

import pytest
from django.utils import timezone

from accounts.models import User
from accounts.tests.conftest import AuthApi
from activities import services, sync
from activities.models import Activity
from activities.sync import SyncCounts, sync_from_intervals
from athletes.models import AthleteProfile
from goals import services as goal_services
from integrations.intervals import (
    IntervalsUnavailableError,
    InvalidKeyError,
    UnexpectedResponseError,
)
from integrations.models import ProviderConnection
from integrations.services import NotConnectedError
from integrations.tests.fake_intervals import FakeIntervals, running
from wellness.models import DailyWellness

from .conftest import make_user, signed_in
from .fit_builder import activity_file
from .gpx_builder import gpx_document
from .tcx_builder import tcx_document

pytestmark = pytest.mark.django_db

URL = "/api/activities/sync/"
PATH = "/api/v1/athlete/0/activities"
WELLNESS_PATH = "/api/v1/athlete/0/wellness"
CHECK = "/api/integrations/intervals/check/"
KEY = "k3y-0123456789-abcdefghij"
NOW = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)
START = datetime(2026, 11, 12, 6, 30, tzinfo=UTC)
BACKEND = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _no_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    """The fake server is on localhost; an environment proxy must not get in the way."""
    for name in ("http_proxy", "HTTP_PROXY", "https_proxy", "HTTPS_PROXY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("no_proxy", "127.0.0.1")


@pytest.fixture(autouse=True)
def _today(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(goal_services, "_utc_now", lambda: NOW)


@pytest.fixture
def fake(settings: Any) -> Iterator[FakeIntervals]:
    """A fake Intervals.icu that the application talks to instead of the real one."""
    with running() as server:
        settings.INTERVALS_API_BASE_URL = server.url
        server.bodies[WELLNESS_PATH] = b"[]"  # most tests only care about activities
        yield server


@pytest.fixture
def alice() -> User:
    return make_user("alice@example.com")


@pytest.fixture
def bob() -> User:
    return make_user("bob@example.com")


def connect(owner: User, key: str = KEY) -> ProviderConnection:
    return ProviderConnection.objects.create(
        owner=owner, provider="intervals_icu", api_key=key, athlete_id="i1"
    )


def connection_of(owner: User) -> ProviderConnection:
    return ProviderConnection.objects.defer("api_key").get(owner=owner)


def entry(
    external_id: str = "i100", start: datetime = START, **fields: object
) -> dict[str, object]:
    return {
        "id": external_id,
        "type": "Run",
        "start_date": start.isoformat(),
        "elapsed_time": 3960,
        "moving_time": 3900,
        "icu_distance": 12000.0,
        "icu_training_load": 75,
        "average_heartrate": 150,
        "max_heartrate": 172,
        "average_speed": 10 / 3,
        "icu_average_watts": 280,
        "total_elevation_gain": 85.7,
        "calories": 820,
        "name": "Morning run with a secret note",
    } | fields


def strava_stub(external_id: str = "s1") -> dict[str, object]:
    return {"id": external_id, "source": "STRAVA", "_note": "STRAVA activities are not available"}


def answer(fake: FakeIntervals, *entries: object) -> None:
    fake.bodies[PATH] = json.dumps(list(entries)).encode()


def wellness_entry(
    day: str = "2026-11-19",
    *,
    sleep_minutes: int | None = 480,
    hrv: float | None = 62.5,
    resting_hr: int | None = 48,
    weight_kg: float | None = 72.4,
) -> dict[str, object]:
    return {
        "id": day,
        "sleepSecs": None if sleep_minutes is None else sleep_minutes * 60,
        "hrv": hrv,
        "restingHR": resting_hr,
        "weight": weight_kg,
    }


def answer_wellness(fake: FakeIntervals, *entries: object) -> None:
    fake.bodies[WELLNESS_PATH] = json.dumps(list(entries)).encode()


def body(response: Any) -> Any:
    return json.loads(response.content)


def activities_of(owner: User) -> list[Activity]:
    return list(Activity.objects.filter(owner=owner).order_by("start_time"))


class TestService:
    def test_it_stores_the_activities_with_their_summary(
        self, fake: FakeIntervals, alice: User
    ) -> None:
        connect(alice)
        answer(fake, entry())

        counts = sync_from_intervals(alice)

        assert counts == SyncCounts(
            imported=1, skipped_duplicates=0, skipped_strava=0, skipped_invalid=0, wellness_synced=0
        )
        [activity] = activities_of(alice)
        assert activity.source == Activity.Source.INTERVALS_ICU
        assert activity.external_id == "i100"
        assert activity.source_hash == ""
        assert (activity.sport, activity.source_sport) == ("running", "Run")
        assert activity.start_time == START
        assert (activity.elapsed_seconds, activity.timer_seconds) == (3960, 3900)
        assert activity.distance_m == 12000
        assert activity.training_load == 75
        assert (activity.avg_heart_rate, activity.max_heart_rate) == (150, 172)
        assert activity.avg_pace_s_per_km == pytest.approx(300)
        assert (activity.avg_power_w, activity.total_ascent_m, activity.calories) == (280, 86, 820)
        assert activity.best_efforts == {}
        assert activity.laps == []
        assert activity.rpe is None
        assert activity.notes == ""

    def test_it_reads_the_configured_number_of_weeks_up_to_today(
        self, fake: FakeIntervals, alice: User, settings: Any
    ) -> None:
        connect(alice)
        answer(fake)
        sync_from_intervals(alice)
        settings.INTERVALS_SYNC_WEEKS = 8
        sync_from_intervals(alice)

        assert [request["path"] for request in fake.requests] == [
            f"{PATH}?oldest=2026-08-27&newest=2026-11-19",
            f"{WELLNESS_PATH}?oldest=2026-08-27&newest=2026-11-19",
            f"{PATH}?oldest=2026-09-24&newest=2026-11-19",
            f"{WELLNESS_PATH}?oldest=2026-09-24&newest=2026-11-19",
        ]

    def test_today_is_the_day_in_the_users_time_zone(
        self, fake: FakeIntervals, alice: User
    ) -> None:
        # 12:00 UTC is already 02:00 of the next day at UTC+14.
        AthleteProfile.objects.create(owner=alice, timezone="Pacific/Kiritimati")
        connect(alice)
        answer(fake)

        sync_from_intervals(alice)

        [activities, wellness] = fake.requests
        assert activities["path"] == f"{PATH}?oldest=2026-08-28&newest=2026-11-20"
        assert wellness["path"] == f"{WELLNESS_PATH}?oldest=2026-08-28&newest=2026-11-20"

    def test_strava_stubs_and_unreadable_entries_are_skipped_and_counted(
        self, fake: FakeIntervals, alice: User
    ) -> None:
        connect(alice)
        answer(fake, strava_stub("s1"), entry(), strava_stub("s2"), {"id": "i9", "type": "Run"})

        counts = sync_from_intervals(alice)

        assert counts == SyncCounts(
            imported=1, skipped_duplicates=0, skipped_strava=2, skipped_invalid=1, wellness_synced=0
        )
        assert [activity.external_id for activity in activities_of(alice)] == ["i100"]

    def test_a_second_sync_imports_nothing(self, fake: FakeIntervals, alice: User) -> None:
        connect(alice)
        answer(fake, entry("i1"), entry("i2", START + timedelta(days=1)))
        assert sync_from_intervals(alice).imported == 2

        counts = sync_from_intervals(alice)

        assert counts == SyncCounts(
            imported=0, skipped_duplicates=2, skipped_strava=0, skipped_invalid=0, wellness_synced=0
        )
        assert Activity.objects.count() == 2

    def test_a_synced_activity_whose_start_changed_is_not_imported_again(
        self, fake: FakeIntervals, alice: User
    ) -> None:
        connect(alice)
        answer(fake, entry("i1"))
        sync_from_intervals(alice)
        answer(fake, entry("i1", START + timedelta(hours=3)))

        assert sync_from_intervals(alice).imported == 0
        assert [activity.start_time for activity in activities_of(alice)] == [START]

    def test_the_same_session_twice_in_one_answer_is_stored_once(
        self, fake: FakeIntervals, alice: User
    ) -> None:
        connect(alice)
        answer(fake, entry("i1"), entry("i2", START + timedelta(seconds=20)))

        counts = sync_from_intervals(alice)

        assert (counts.imported, counts.skipped_duplicates) == (1, 1)
        assert [activity.external_id for activity in activities_of(alice)] == ["i1"]

    @pytest.mark.parametrize(
        "upload",
        [
            pytest.param(lambda: activity_file(start=START), id="fit"),
            pytest.param(lambda: tcx_document(), id="tcx"),
            pytest.param(lambda: gpx_document(), id="gpx"),
        ],
    )
    def test_an_uploaded_file_of_the_same_session_is_not_imported_again(
        self, fake: FakeIntervals, alice: User, upload: Callable[[], bytes]
    ) -> None:
        stored = services.import_activity(alice, upload())
        seconds = stored.timer_seconds or stored.elapsed_seconds
        connect(alice)
        # Intervals.icu read the same file: the start is a few seconds off, the duration close.
        answer(
            fake,
            entry(
                start=stored.start_time + timedelta(seconds=5),
                moving_time=seconds,
                elapsed_time=seconds,
            ),
        )

        counts = sync_from_intervals(alice)

        assert (counts.imported, counts.skipped_duplicates) == (0, 1)
        assert activities_of(alice) == [stored]

    def test_a_manual_entry_of_the_same_session_is_not_imported_again(
        self, fake: FakeIntervals, alice: User
    ) -> None:
        manual = services.enter_activity(
            alice, sport="running", start=START + timedelta(minutes=2), duration_minutes=65
        )
        connect(alice)
        answer(fake, entry())

        counts = sync_from_intervals(alice)

        assert (counts.imported, counts.skipped_duplicates) == (0, 1)
        assert activities_of(alice) == [manual]

    def test_another_sport_at_the_same_time_is_a_session_of_its_own(
        self, fake: FakeIntervals, alice: User
    ) -> None:
        services.enter_activity(alice, sport="running", start=START, duration_minutes=65)
        connect(alice)
        answer(fake, entry(type="Ride"))

        assert sync_from_intervals(alice).imported == 1
        assert sorted(a.sport for a in activities_of(alice)) == ["cycling", "running"]

    def test_the_estimates_are_refreshed_only_when_something_was_imported(
        self, fake: FakeIntervals, alice: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        refreshed: list[User] = []
        monkeypatch.setattr(sync, "refresh_estimates_safely", refreshed.append)
        connect(alice)
        answer(fake, entry())

        sync_from_intervals(alice)
        sync_from_intervals(alice)

        assert refreshed == [alice]

    def test_success_records_the_time_and_clears_an_earlier_error(
        self, fake: FakeIntervals, alice: User
    ) -> None:
        connection = connect(alice)
        connection.last_sync_error = "unavailable"
        connection.save()
        answer(fake)
        before = timezone.now()

        sync_from_intervals(alice)

        connection = connection_of(alice)
        assert connection.last_sync_error == ""
        assert connection.last_sync_at is not None
        assert before <= connection.last_sync_at <= timezone.now()

    def test_without_a_connection_nothing_is_asked(self, fake: FakeIntervals, alice: User) -> None:
        with pytest.raises(NotConnectedError):
            sync_from_intervals(alice)

        assert fake.requests == []
        assert not Activity.objects.exists()

    @pytest.mark.parametrize(
        ("status", "raised", "code"),
        [
            (401, InvalidKeyError, "invalid_key"),
            (403, InvalidKeyError, "invalid_key"),
            (429, IntervalsUnavailableError, "unavailable"),
            (503, IntervalsUnavailableError, "unavailable"),
            (418, UnexpectedResponseError, "unexpected"),
        ],
    )
    def test_a_failure_records_its_code_and_keeps_the_last_sync_time(
        self,
        fake: FakeIntervals,
        alice: User,
        status: int,
        raised: type[Exception],
        code: str,
    ) -> None:
        connection = connect(alice)
        earlier = timezone.now() - timedelta(days=2)
        connection.last_sync_at = earlier
        connection.save()
        answer(fake, entry())
        fake.status = status

        with pytest.raises(raised):
            sync_from_intervals(alice)

        connection = connection_of(alice)
        assert connection.last_sync_error == code
        assert connection.last_sync_at == earlier
        assert not Activity.objects.exists()

    def test_a_refused_key_marks_the_connection_invalid(
        self, fake: FakeIntervals, alice: User
    ) -> None:
        connect(alice)
        fake.status = 401

        with pytest.raises(InvalidKeyError):
            sync_from_intervals(alice)

        assert connection_of(alice).status == "invalid"

    def test_an_answer_that_is_no_list_is_unexpected(
        self, fake: FakeIntervals, alice: User
    ) -> None:
        connect(alice)
        fake.bodies[PATH] = b'{"not": "a list"}'

        with pytest.raises(UnexpectedResponseError):
            sync_from_intervals(alice)

        assert connection_of(alice).last_sync_error == "unexpected"
        assert connection_of(alice).last_sync_at is None

    def test_no_name_or_note_from_intervals_is_stored(
        self, fake: FakeIntervals, alice: User
    ) -> None:
        connect(alice)
        answer(fake, entry(description="secret description"))

        sync_from_intervals(alice)

        values = Activity.objects.values().get()
        assert "secret" not in json.dumps(values, default=str)

    def test_it_imports_wellness_alongside_activities(
        self, fake: FakeIntervals, alice: User
    ) -> None:
        connect(alice)
        answer(fake, entry())
        answer_wellness(fake, wellness_entry("2026-11-19", sleep_minutes=480))

        counts = sync_from_intervals(alice)

        assert counts.wellness_synced == 1
        stored = DailyWellness.objects.for_user(alice).get(day=date(2026, 11, 19))
        assert stored.sleep_minutes == 480

    def test_a_repeat_sync_is_idempotent_for_wellness(
        self, fake: FakeIntervals, alice: User
    ) -> None:
        connect(alice)
        answer(fake, entry())
        answer_wellness(fake, wellness_entry("2026-11-19", sleep_minutes=480))
        assert sync_from_intervals(alice).wellness_synced == 1
        before = DailyWellness.objects.for_user(alice).get(day=date(2026, 11, 19)).updated_at

        counts = sync_from_intervals(alice)

        assert counts.wellness_synced == 0
        after = DailyWellness.objects.for_user(alice).get(day=date(2026, 11, 19))
        assert after.updated_at == before
        assert DailyWellness.objects.count() == 1

    def test_a_wellness_fetch_error_records_its_code_and_imports_nothing(
        self, fake: FakeIntervals, alice: User
    ) -> None:
        connect(alice)
        answer(fake, entry())
        fake.bodies[WELLNESS_PATH] = b'{"not": "a list"}'

        with pytest.raises(UnexpectedResponseError):
            sync_from_intervals(alice)

        assert connection_of(alice).last_sync_error == "unexpected"
        assert not Activity.objects.exists()
        assert not DailyWellness.objects.exists()


class TestIsolation:
    def test_it_uses_only_the_key_of_the_user_and_writes_only_their_data(
        self, fake: FakeIntervals, alice: User, bob: User
    ) -> None:
        connect(alice, "alice-key-0123456789")
        connect(bob, "bob-key-0123456789")
        answer(fake, entry())

        sync_from_intervals(alice)

        [request, *rest] = fake.requests
        expected = base64.b64encode(b"API_KEY:alice-key-0123456789").decode()
        assert request["headers"]["Authorization"] == f"Basic {expected}"
        assert all(r["headers"]["Authorization"] == f"Basic {expected}" for r in rest)
        assert len(activities_of(alice)) == 1
        assert activities_of(bob) == []
        assert connection_of(alice).last_sync_at is not None
        assert connection_of(bob).last_sync_at is None

    def test_another_users_activities_are_no_duplicates(
        self, fake: FakeIntervals, alice: User, bob: User
    ) -> None:
        connect(alice)
        connect(bob)
        services.enter_activity(bob, sport="running", start=START, duration_minutes=65)
        answer(fake, entry())
        sync_from_intervals(bob)  # the manual entry: skipped for bob
        assert len(activities_of(bob)) == 1

        assert sync_from_intervals(alice).imported == 1
        assert sync_from_intervals(bob).imported == 0
        assert [a.source for a in activities_of(bob)] == ["manual"]

    def test_the_same_intervals_id_is_stored_for_each_user(
        self, fake: FakeIntervals, alice: User, bob: User
    ) -> None:
        connect(alice)
        connect(bob)
        answer(fake, entry("i1"))

        sync_from_intervals(alice)

        assert sync_from_intervals(bob).imported == 1

    def test_a_failure_is_recorded_only_on_the_users_connection(
        self, fake: FakeIntervals, alice: User, bob: User
    ) -> None:
        connect(alice)
        connect(bob)
        fake.status = 503

        with pytest.raises(IntervalsUnavailableError):
            sync_from_intervals(alice)

        assert connection_of(alice).last_sync_error == "unavailable"
        assert connection_of(bob).last_sync_error == ""

    def test_each_users_wellness_is_kept_apart(
        self, fake: FakeIntervals, alice: User, bob: User
    ) -> None:
        connect(alice)
        connect(bob)
        answer(fake, entry())
        answer_wellness(fake, wellness_entry("2026-11-19", sleep_minutes=480))

        sync_from_intervals(alice)
        answer_wellness(fake, wellness_entry("2026-11-19", sleep_minutes=360))
        sync_from_intervals(bob)

        alices = DailyWellness.objects.for_user(alice).get(day=date(2026, 11, 19))
        bobs = DailyWellness.objects.for_user(bob).get(day=date(2026, 11, 19))
        assert alices.sleep_minutes == 480
        assert bobs.sleep_minutes == 360


class TestEndpoint:
    def test_it_imports_and_answers_with_the_counts_and_the_sync_time(
        self, fake: FakeIntervals, alice: User
    ) -> None:
        connect(alice)
        answer(fake, entry(), strava_stub())
        api = signed_in(alice)

        response = api.call("POST", URL)

        assert response.status_code == HTTPStatus.OK
        data = body(response)
        assert data.pop("last_sync_at").endswith("Z")
        assert data == {
            "imported": 1,
            "skipped_duplicates": 0,
            "skipped_strava": 1,
            "skipped_invalid": 0,
            "wellness_synced": 0,
        }
        [listed] = body(api.call("GET", "/api/activities/"))["results"]
        assert listed["source"] == "intervals_icu"
        assert listed["training_load"] == 75
        assert "external_id" not in listed

    def test_a_second_sync_imports_nothing(self, fake: FakeIntervals, alice: User) -> None:
        connect(alice)
        answer(fake, entry())
        api = signed_in(alice)
        api.call("POST", URL)

        data = body(api.call("POST", URL))

        assert (data["imported"], data["skipped_duplicates"]) == (0, 1)
        assert Activity.objects.count() == 1

    def test_without_a_connection_it_is_a_404_and_nothing_is_asked(
        self, fake: FakeIntervals, alice: User
    ) -> None:
        response = signed_in(alice).call("POST", URL)

        assert response.status_code == HTTPStatus.NOT_FOUND
        assert body(response) == {"detail": "Not connected."}
        assert fake.requests == []

    @pytest.mark.parametrize("status", [401, 403])
    def test_a_refused_key_is_a_409(self, fake: FakeIntervals, alice: User, status: int) -> None:
        connect(alice)
        fake.status = status

        response = signed_in(alice).call("POST", URL)

        assert response.status_code == HTTPStatus.CONFLICT
        assert body(response) == {
            "detail": "Intervals.icu did not accept the stored API key. "
            "Enter it again on the Connections page."
        }
        assert connection_of(alice).last_sync_error == "invalid_key"

    @pytest.mark.parametrize("status", [429, 500, 503])
    def test_an_unreachable_service_is_a_503(
        self, fake: FakeIntervals, alice: User, status: int
    ) -> None:
        connect(alice)
        fake.status = status

        response = signed_in(alice).call("POST", URL)

        assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
        assert body(response) == {
            "detail": "Intervals.icu cannot be reached right now. Please try again later."
        }
        assert connection_of(alice).last_sync_error == "unavailable"

    def test_an_odd_answer_is_a_502(self, fake: FakeIntervals, alice: User) -> None:
        connect(alice)
        fake.bodies[PATH] = b'{"not": "a list"}'

        response = signed_in(alice).call("POST", URL)

        assert response.status_code == HTTPStatus.BAD_GATEWAY
        assert body(response) == {
            "detail": "Intervals.icu answered in an unexpected way. Please try again later."
        }
        assert connection_of(alice).last_sync_error == "unexpected"

    def test_no_answer_contains_the_key(self, fake: FakeIntervals, alice: User) -> None:
        connect(alice)
        api = signed_in(alice)
        for status in (200, 401, 503, 418):
            fake.status = status
            answer(fake, entry())
            assert KEY not in api.call("POST", URL).content.decode()

    def test_anonymous_visitors_are_refused(self, fake: FakeIntervals) -> None:
        assert AuthApi().call("POST", URL).status_code == HTTPStatus.FORBIDDEN
        assert fake.requests == []

    def test_only_post_is_allowed(self, fake: FakeIntervals, alice: User) -> None:
        connect(alice)
        api = signed_in(alice)

        for method in ("GET", "PUT", "PATCH", "DELETE"):
            assert api.call(method, URL).status_code == HTTPStatus.METHOD_NOT_ALLOWED
        assert fake.requests == []

    def test_it_is_not_taken_for_an_activity_id(self, fake: FakeIntervals, alice: User) -> None:
        connect(alice)
        answer(fake)

        assert signed_in(alice).call("POST", URL).status_code == HTTPStatus.OK


class TestEndpointIsolation:
    def test_it_syncs_only_the_signed_in_user(
        self, fake: FakeIntervals, alice: User, bob: User
    ) -> None:
        connect(alice, "alice-key-0123456789")
        connect(bob, "bob-key-0123456789")
        answer(fake, entry())

        signed_in(alice).call("POST", URL)

        [request, *rest] = fake.requests
        expected = base64.b64encode(b"API_KEY:alice-key-0123456789").decode()
        assert request["headers"]["Authorization"] == f"Basic {expected}"
        assert all(r["headers"]["Authorization"] == f"Basic {expected}" for r in rest)
        assert body(signed_in(bob).call("GET", "/api/activities/"))["results"] == []
        assert connection_of(bob).last_sync_at is None

    def test_another_users_connection_is_not_used(
        self, fake: FakeIntervals, alice: User, bob: User
    ) -> None:
        connect(bob)

        response = signed_in(alice).call("POST", URL)

        assert response.status_code == HTTPStatus.NOT_FOUND
        assert fake.requests == []
        assert connection_of(bob).last_sync_error == ""


class TestThrottle:
    def test_the_eleventh_call_within_a_minute_is_throttled_and_never_asks(
        self, fake: FakeIntervals, alice: User
    ) -> None:
        connect(alice)
        answer(fake)
        api = signed_in(alice)
        for _ in range(10):
            assert api.call("POST", URL).status_code == HTTPStatus.OK

        response = api.call("POST", URL)

        assert response.status_code == HTTPStatus.TOO_MANY_REQUESTS
        assert "Retry-After" in response.headers
        assert len(fake.requests) == 20  # ten syncs, each asking for activities and wellness

    def test_it_shares_the_counter_with_checking_the_connection(
        self, fake: FakeIntervals, alice: User
    ) -> None:
        connect(alice)
        answer(fake)
        api = signed_in(alice)
        for _ in range(5):
            api.call("POST", URL)
            api.call("POST", CHECK)

        assert api.call("POST", URL).status_code == HTTPStatus.TOO_MANY_REQUESTS
        assert api.call("POST", CHECK).status_code == HTTPStatus.TOO_MANY_REQUESTS

    def test_another_user_is_not_throttled(
        self, fake: FakeIntervals, alice: User, bob: User
    ) -> None:
        connect(alice)
        connect(bob)
        answer(fake)
        alices = signed_in(alice)
        for _ in range(11):
            alices.call("POST", URL)

        assert signed_in(bob).call("POST", URL).status_code == HTTPStatus.OK


class TestSetting:
    def test_the_default_is_twelve_weeks(self) -> None:
        result = _import_settings(check="print(config.settings.INTERVALS_SYNC_WEEKS)")

        assert result.returncode == 0
        assert result.stdout.strip() == "12"

    @pytest.mark.parametrize("value", ["8", "10", "12"])
    def test_eight_to_twelve_weeks_are_read_from_the_environment(self, value: str) -> None:
        result = _import_settings(
            INTERVALS_SYNC_WEEKS=value, check="print(config.settings.INTERVALS_SYNC_WEEKS)"
        )

        assert result.returncode == 0
        assert result.stdout.strip() == value

    @pytest.mark.parametrize("value", ["7", "13", "0", "-8", "lots", "10.5", ""])
    def test_any_other_value_fails_at_startup(self, value: str) -> None:
        result = _import_settings(INTERVALS_SYNC_WEEKS=value)

        assert result.returncode != 0

    def test_a_value_out_of_range_is_explained(self) -> None:
        result = _import_settings(INTERVALS_SYNC_WEEKS="13")

        assert "INTERVALS_SYNC_WEEKS must be a whole number from 8 to 12" in result.stderr


def _import_settings(check: str = "pass", **env: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ | {
        "DJANGO_SECRET_KEY": "x",
        "DATABASE_URL": "sqlite:///unused.db",
        "ENCRYPTION_KEY": "srPGFiK_-1uuYQrhJix9QxALddGxwSw-I5bllic4QsY=",
    }
    environment.pop("INTERVALS_SYNC_WEEKS", None)
    return subprocess.run(
        [sys.executable, "-c", f"import config.settings; {check}"],
        env=environment | env,
        cwd=BACKEND,
        capture_output=True,
        text=True,
    )
