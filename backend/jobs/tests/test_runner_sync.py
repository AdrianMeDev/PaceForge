"""The sync job: every outcome is one log row with a fixed code, and never an exception."""

import base64
import json
from collections.abc import Iterator
from datetime import datetime, timedelta
from http import HTTPStatus
from typing import Any

import pytest

from accounts.models import User
from activities.models import Activity
from integrations.models import ProviderConnection
from integrations.tests.fake_intervals import FakeIntervals, running
from jobs.models import Code, Job, JobRun, JobSettings, Outcome
from jobs.runner import run_sync

from .conftest import NOW, make_user

pytestmark = pytest.mark.django_db

PATH = "/api/v1/athlete/0/activities"


@pytest.fixture
def fake(settings: Any) -> Iterator[FakeIntervals]:
    """A fake Intervals.icu that the job talks to instead of the real one."""
    with running() as server:
        settings.INTERVALS_API_BASE_URL = server.url  # the fixture undoes it after the test
        yield server


def connect(owner: User, key: str = "k3y-0123456789-abcdefghij") -> ProviderConnection:
    return ProviderConnection.objects.create(
        owner=owner, provider="intervals_icu", api_key=key, athlete_id="i1"
    )


def answer(fake: FakeIntervals, *entries: object) -> None:
    fake.bodies[PATH] = json.dumps(list(entries)).encode()


def entry(external_id: str, start: datetime) -> dict[str, object]:
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
    }


def authorization_of(key: str) -> str:
    return "Basic " + base64.b64encode(f"API_KEY:{key}".encode()).decode("ascii")


def test_a_user_with_the_sync_turned_off_never_reaches_intervals(fake: FakeIntervals) -> None:
    user = make_user("off@example.com")
    connect(user)
    JobSettings.objects.create(owner=user, sync=False)

    assert run_sync(user) is None

    assert JobRun.objects.count() == 0
    assert fake.requests == []


def test_a_user_without_a_connection_is_skipped(fake: FakeIntervals) -> None:
    user = make_user("lonely@example.com")

    run = run_sync(user)
    assert run is not None

    assert (run.job, run.outcome, run.code) == (Job.SYNC, Outcome.SKIPPED, Code.NOT_CONNECTED)
    assert run.counts == {}
    assert fake.requests == []


def test_a_refused_key_is_a_failure_with_a_fixed_code(fake: FakeIntervals) -> None:
    user = make_user("refused@example.com")
    connect(user)
    fake.bodies[PATH] = b"[]"
    fake.queue(HTTPStatus.UNAUTHORIZED, body=b'{"message": "bad key"}')

    run = run_sync(user)
    assert run is not None

    assert (run.outcome, run.code) == (Outcome.FAILED, Code.INVALID_KEY)
    assert run.counts == {}
    assert not Activity.objects.exists()


def test_an_unreadable_answer_is_a_failure_with_a_fixed_code(fake: FakeIntervals) -> None:
    user = make_user("garbled@example.com")
    connect(user)
    fake.bodies[PATH] = b"not json at all"

    run = run_sync(user)
    assert run is not None

    assert (run.outcome, run.code) == (Outcome.FAILED, Code.INTERVALS_UNAVAILABLE)
    assert run.counts == {}
    assert not Activity.objects.exists()
    # No word of the provider's answer is in the log, only the fixed code.
    assert json.dumps({"code": run.code, "counts": run.counts}) == json.dumps(
        {"code": Code.INTERVALS_UNAVAILABLE, "counts": {}}
    )


def test_a_successful_sync_is_done_with_its_counts(fake: FakeIntervals) -> None:
    user = make_user("fine@example.com")
    connect(user)
    answer(fake, entry("i100", NOW), {"id": "s1", "source": "STRAVA"})

    run = run_sync(user)
    assert run is not None

    assert (run.outcome, run.code) == (Outcome.DONE, "")
    assert run.counts == {
        "imported": 1,
        "skipped_duplicates": 0,
        "skipped_strava": 1,
        "skipped_invalid": 0,
    }
    assert [a.external_id for a in Activity.objects.for_user(user)] == ["i100"]


def test_two_users_each_get_only_their_own_activities_and_runs(fake: FakeIntervals) -> None:
    alice = make_user("alice@example.com")
    bob = make_user("bob@example.com")
    alice_key, bob_key = "k3y-alice-0000000000", "k3y-bob-00000000000"
    connect(alice, alice_key)
    connect(bob, bob_key)

    fake.queue(body=json.dumps([entry("a1", NOW)]).encode())
    alice_run = run_sync(alice)
    fake.queue(body=json.dumps([entry("b1", NOW), entry("b2", NOW - timedelta(hours=2))]).encode())
    bob_run = run_sync(bob)
    assert alice_run is not None and bob_run is not None

    assert [a.external_id for a in Activity.objects.for_user(alice).order_by("external_id")] == [
        "a1"
    ]
    assert [a.external_id for a in Activity.objects.for_user(bob).order_by("external_id")] == [
        "b1",
        "b2",
    ]
    assert (alice_run.owner, alice_run.counts["imported"]) == (alice, 1)
    assert (bob_run.owner, bob_run.counts["imported"]) == (bob, 2)
    assert set(JobRun.objects.values_list("owner_id", flat=True)) == {alice.id, bob.id}
    # Each sync used the key of its own user, and only it.
    authorizations = [request["headers"].get("Authorization") for request in fake.requests]
    assert authorizations == [authorization_of(alice_key), authorization_of(bob_key)]


def test_the_log_holds_only_fixed_words(fake: FakeIntervals) -> None:
    user = make_user("checked@example.com")
    connect(user)
    fake.bodies[PATH] = b'{"message": "provider says: internal secret"}'

    run = run_sync(user)
    assert run is not None

    assert run.code in Code.values
