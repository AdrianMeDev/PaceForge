"""The per-job management commands: looping over users, each in their own context.

Each command runs its job for every active account, ordered by ``pk``, without mixing data. The
draft command syncs first. One account that crashes never stops the others, and its failure is a
``failed/unexpected`` row. The output is counts only.
"""

import json
from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from django.core.management import call_command

from accounts.models import User
from activities.models import Activity
from integrations.models import ProviderConnection
from integrations.tests.fake_intervals import FakeIntervals, running
from jobs.models import Code, Job, JobRun, Outcome
from planning.models import WeeklyPlan
from planning.schema import Goal, Sport, WeekPlan, Workout, ZoneSystem, to_json
from planning.tests.scripted import Scripted
from reviews.models import WeekComment
from wellness.models import DailyWellness

from .conftest import NOW, make_user

pytestmark = pytest.mark.django_db

# The clock of the jobs tests is a Thursday; its week starts on Monday the 16th.
THIS_MONDAY = date(2026, 11, 16)
NEXT_MONDAY = THIS_MONDAY + timedelta(weeks=1)
KEY = "synthetic-test-token-abcdefghij"
PATH = "/api/v1/athlete/0/activities"
WELLNESS_PATH = "/api/v1/athlete/0/wellness"
Status = WeeklyPlan.Status


@pytest.fixture
def fake(settings: Any) -> Iterator[FakeIntervals]:
    """A fake Intervals.icu that the sync part of a command talks to instead of the real one."""
    with running() as server:
        settings.INTERVALS_API_BASE_URL = server.url  # the fixture undoes it after the test
        server.bodies[WELLNESS_PATH] = b"[]"  # sync asks for wellness too
        yield server


@pytest.fixture
def provide(monkeypatch: pytest.MonkeyPatch) -> Callable[..., Scripted]:
    """Install a provider that answers from a list, in place of the user's real one."""
    from coach import services as coach_services

    def install(*replies: Any) -> Scripted:
        scripted = Scripted(*replies)
        monkeypatch.setattr(
            coach_services, "provider_for", lambda configuration, model=None, effort="": scripted
        )
        return scripted

    return install


def connect(owner: User, key: str = "k3y-0123456789-abcdefghij") -> ProviderConnection:
    return ProviderConnection.objects.create(
        owner=owner, provider="intervals_icu", api_key=key, athlete_id="i1"
    )


def answer(fake: FakeIntervals, *entries: object) -> None:
    fake.bodies[PATH] = json.dumps(list(entries)).encode()


def wellness_entry(day: str, *, sleep_minutes: int = 480) -> dict[str, object]:
    return {
        "id": day,
        "sleepSecs": sleep_minutes * 60,
        "hrv": 62.5,
        "restingHR": 48,
        "weight": 72.4,
    }


def answer_wellness(fake: FakeIntervals, *entries: object) -> None:
    fake.bodies[WELLNESS_PATH] = json.dumps(list(entries)).encode()


def queue_sync(fake: FakeIntervals, *activity_bodies: list[dict[str, object]]) -> None:
    """Queue one sync per user: their activities followed by an empty wellness answer."""
    for activities in activity_bodies:
        fake.queue(body=json.dumps(activities).encode())
        fake.queue(body=b"[]")


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
        "name": "Morning run",
    }


def athlete(email: str, *, minutes: list[int] | None = None) -> User:
    """A user with training time and a coach configured, ready for a draft."""
    from athletes.models import ThresholdValue
    from availability.models import WeekdayMinutes
    from coach.models import AIProviderConfiguration

    user = make_user(email)
    for weekday, value in enumerate(
        minutes if minutes is not None else [90, 0, 90, 0, 120, 120, 0]
    ):
        WeekdayMinutes.objects.create(owner=user, weekday=weekday, minutes=value)
    ThresholdValue.objects.create(
        owner=user, sport="ride", metric="ftp", value=250, source="manual", basis="test"
    )
    AIProviderConfiguration.objects.create(
        owner=user, provider="anthropic", model="claude-sonnet-5-5", api_key=KEY
    )
    return user


def activity_in(user: User, week: date, day: int) -> None:
    Activity.objects.create(
        owner=user,
        source="manual",
        sport="running",
        start_time=datetime.combine(week + timedelta(days=day), datetime.min.time(), tzinfo=UTC),
        timer_seconds=3600.0,
    )


def ride(offset: int, monday: date = NEXT_MONDAY) -> Workout:
    return Workout(
        day=monday + timedelta(days=offset),
        sport=Sport.CYCLING,
        title="Endurance ride",
        goal=Goal.ENDURANCE,
        duration_minutes=60,
        zone_system=ZoneSystem.POWER,
        zone=2,
    )


def good_plan() -> str:
    return json.dumps(to_json(WeekPlan(NEXT_MONDAY, (ride(0), ride(2)), "Base")))


def good_comment() -> str:
    return json.dumps({"comment": "A steady week.", "next_week": "hold"})


class TestSyncActivities:
    def test_two_users_each_get_only_their_own_activities_and_runs(
        self, fake: FakeIntervals
    ) -> None:
        alice = make_user("alice@example.com")
        bob = make_user("bob@example.com")
        alice_key, bob_key = "k3y-alice-0000000000", "k3y-bob-00000000000"
        connect(alice, alice_key)
        connect(bob, bob_key)
        queue_sync(
            fake,
            [entry("a1", NOW)],
            [entry("b1", NOW), entry("b2", NOW - timedelta(hours=2))],
        )

        call_command("sync_activities")

        assert [
            a.external_id for a in Activity.objects.for_user(alice).order_by("external_id")
        ] == ["a1"]
        assert [a.external_id for a in Activity.objects.for_user(bob).order_by("external_id")] == [
            "b1",
            "b2",
        ]
        runs = {r.owner_id: r for r in JobRun.objects.filter(job=Job.SYNC)}
        assert set(runs) == {alice.id, bob.id}
        assert runs[alice.id].counts["imported"] == 1
        assert runs[bob.id].counts["imported"] == 2
        assert {r.outcome for r in runs.values()} == {Outcome.DONE}

    def test_each_users_wellness_is_synced_separately(self, fake: FakeIntervals) -> None:
        alice = make_user("alice@example.com")
        bob = make_user("bob@example.com")
        connect(alice)
        connect(bob)
        # Each sync asks twice: activities, then wellness; give both users their own wellness.
        fake.queue(body=json.dumps([entry("a1", NOW)]).encode())
        fake.queue(body=json.dumps([wellness_entry("2026-11-19", sleep_minutes=480)]).encode())
        fake.queue(body=json.dumps([entry("b1", NOW)]).encode())
        fake.queue(body=json.dumps([wellness_entry("2026-11-19", sleep_minutes=360)]).encode())

        call_command("sync_activities")

        alices = DailyWellness.objects.for_user(alice).get(day=date(2026, 11, 19))
        bobs = DailyWellness.objects.for_user(bob).get(day=date(2026, 11, 19))
        assert (alices.sleep_minutes, bobs.sleep_minutes) == (480, 360)
        runs = {r.owner_id: r for r in JobRun.objects.filter(job=Job.SYNC)}
        assert runs[alice.id].counts["wellness_synced"] == 1
        assert runs[bob.id].counts["wellness_synced"] == 1

    def test_an_inactive_user_is_not_synced(self, fake: FakeIntervals) -> None:
        active = make_user("active@example.com")
        idle = make_user("idle@example.com")
        connect(active)
        connect(idle)
        idle.is_active = False
        idle.save(update_fields=["is_active"])
        queue_sync(fake, [entry("a1", NOW)])

        call_command("sync_activities")

        assert [a.external_id for a in Activity.objects.for_user(active)] == ["a1"]
        assert not Activity.objects.for_user(idle).exists()
        assert set(JobRun.objects.values_list("owner_id", flat=True)) == {active.id}

    def test_email_runs_one_account(self, fake: FakeIntervals) -> None:
        alice = make_user("alice@example.com")
        bob = make_user("bob@example.com")
        connect(alice)
        connect(bob)
        fake.bodies[PATH] = json.dumps([entry("a1", NOW)]).encode()

        call_command("sync_activities", email="alice@example.com")

        assert [a.external_id for a in Activity.objects.for_user(alice)] == ["a1"]
        assert not Activity.objects.for_user(bob).exists()
        assert set(JobRun.objects.values_list("owner_id", flat=True)) == {alice.id}


class TestDraftNextWeek:
    def test_syncs_before_it_drafts_each_user(
        self, fake: FakeIntervals, provide: Callable[..., Scripted]
    ) -> None:
        alice = athlete("alice@example.com")
        bob = athlete("bob@example.com")
        connect(alice)
        connect(bob)
        # Each sync asks for activities then wellness; give both users their own wellness.
        fake.queue(body=json.dumps([entry("a1", NOW)]).encode())
        fake.queue(body=json.dumps([wellness_entry("2026-11-19", sleep_minutes=480)]).encode())
        fake.queue(body=json.dumps([entry("b1", NOW)]).encode())
        fake.queue(body=json.dumps([wellness_entry("2026-11-19", sleep_minutes=360)]).encode())
        # Two replies per user: the synced run changes the volume, so a repair is asked.
        provide(good_plan(), good_plan(), good_plan(), good_plan())

        call_command("draft_next_week")

        # Each user's own activity was imported, and only their own draft was stored.
        assert [
            a.external_id for a in Activity.objects.for_user(alice).order_by("external_id")
        ] == ["a1"]
        assert [a.external_id for a in Activity.objects.for_user(bob).order_by("external_id")] == [
            "b1"
        ]
        plans = {p.owner_id: p for p in WeeklyPlan.objects.filter(owner__in=[alice, bob])}
        assert set(plans) == {alice.id, bob.id}
        assert {p.status for p in plans.values()} == {Status.DRAFT}
        # Wellness is also stored per user.
        alices = DailyWellness.objects.for_user(alice).get(day=date(2026, 11, 19))
        bobs = DailyWellness.objects.for_user(bob).get(day=date(2026, 11, 19))
        assert (alices.sleep_minutes, bobs.sleep_minutes) == (480, 360)
        # Each sync ran before its draft.
        for user in (alice, bob):
            sync_run = JobRun.objects.get(owner=user, job=Job.SYNC)
            draft_run = JobRun.objects.get(owner=user, job=Job.WEEK_DRAFT)
            assert sync_run.outcome == Outcome.DONE
            assert draft_run.outcome == Outcome.DONE
            assert draft_run.week_start == NEXT_MONDAY
            assert sync_run.started_at <= draft_run.started_at

    def test_a_crash_for_one_user_still_runs_the_other(
        self, fake: FakeIntervals, provide: Callable[..., Scripted], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        alice = athlete("alice@example.com")
        bob = athlete("bob@example.com")
        connect(alice)
        connect(bob)
        queue_sync(fake, [entry("a1", NOW)], [entry("b1", NOW)])
        # Bob's synced run still changes the volume, so his draft asks twice.
        provide(good_plan(), good_plan())

        # Alice's draft blows up in a way the job does not expect.
        from jobs import runner

        real_run_draft = runner.run_draft

        def crashing_run_draft(user: User, monday: date) -> Any:
            if user == alice:
                raise RuntimeError("boom")
            return real_run_draft(user, monday)

        monkeypatch.setattr(runner, "run_draft", crashing_run_draft)

        call_command("draft_next_week")

        # Alice got a failed/unexpected draft run; Bob still got his plan.
        alice_run = JobRun.objects.get(owner=alice, job=Job.WEEK_DRAFT)
        assert (alice_run.outcome, alice_run.code) == (Outcome.FAILED, Code.UNEXPECTED)
        bob_run = JobRun.objects.get(owner=bob, job=Job.WEEK_DRAFT)
        assert bob_run.outcome == Outcome.DONE
        assert WeeklyPlan.objects.for_user(bob).get().status == Status.DRAFT

    def test_email_limits_the_draft_to_one_account(
        self, fake: FakeIntervals, provide: Callable[..., Scripted]
    ) -> None:
        alice = athlete("alice@example.com")
        bob = athlete("bob@example.com")
        connect(alice)
        connect(bob)
        queue_sync(fake, [entry("a1", NOW)])
        provide(good_plan(), good_plan())

        call_command("draft_next_week", email="alice@example.com")

        assert WeeklyPlan.objects.for_user(alice).exists()
        assert not WeeklyPlan.objects.for_user(bob).exists()
        assert set(JobRun.objects.values_list("owner_id", flat=True)) == {alice.id}


class TestReviewWeeks:
    def test_two_users_each_get_their_own_comment(self, provide: Callable[..., Scripted]) -> None:
        alice = athlete("alice@example.com")
        bob = athlete("bob@example.com")
        activity_in(alice, THIS_MONDAY, 1)
        activity_in(bob, THIS_MONDAY, 2)
        provide(good_comment(), json.dumps({"comment": "More volume.", "next_week": "increase"}))

        call_command("review_weeks")

        assert WeekComment.objects.for_user(alice).get().comment == "A steady week."
        assert WeekComment.objects.for_user(bob).get().comment == "More volume."
        runs = {r.owner_id: r for r in JobRun.objects.filter(job=Job.WEEK_REVIEW)}
        assert set(runs) == {alice.id, bob.id}
        assert runs[alice.id].week_start == THIS_MONDAY
        assert runs[bob.id].week_start == THIS_MONDAY

    def test_a_crash_for_one_user_still_runs_the_other(
        self, provide: Callable[..., Scripted], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        alice = athlete("alice@example.com")
        bob = athlete("bob@example.com")
        activity_in(alice, THIS_MONDAY, 1)
        activity_in(bob, THIS_MONDAY, 2)
        provide(good_comment())

        from jobs import runner

        real_run_review = runner.run_review

        def crashing_run_review(user: User, monday: date) -> Any:
            if user == alice:
                raise RuntimeError("boom")
            return real_run_review(user, monday)

        monkeypatch.setattr(runner, "run_review", crashing_run_review)

        call_command("review_weeks")

        alice_run = JobRun.objects.get(owner=alice, job=Job.WEEK_REVIEW)
        assert (alice_run.outcome, alice_run.code) == (Outcome.FAILED, Code.UNEXPECTED)
        bob_run = JobRun.objects.get(owner=bob, job=Job.WEEK_REVIEW)
        assert bob_run.outcome == Outcome.DONE
        assert WeekComment.objects.for_user(bob).get().comment == "A steady week."
