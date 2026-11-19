"""The scheduler: which jobs are due, once per week, capped on failure, one round per user."""

import json
import subprocess
import sys
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from accounts.models import User
from activities.models import Activity
from athletes.models import AthleteProfile
from integrations.tests.fake_intervals import FakeIntervals
from jobs import schedule
from jobs.models import Code, Job, JobRun, JobSettings, Outcome
from jobs.services import record
from planning.models import WeeklyPlan
from planning.tests.scripted import Scripted
from reviews.models import WeekComment
from wellness.models import DailyWellness

from .conftest import make_user
from .test_commands import (
    NEXT_MONDAY,
    THIS_MONDAY,
    activity_in,
    answer,
    athlete,
    connect,
    entry,
    fake,  # noqa: F401  (fixture)
    good_comment,
    good_plan,
    provide,  # noqa: F401  (fixture)
    wellness_entry,
)

pytestmark = pytest.mark.django_db

# The Sunday that ends the week of THIS_MONDAY, 18:30 in Berlin (UTC+1 in November).
SUNDAY = datetime(2026, 11, 22, 17, 30, tzinfo=UTC)


def zone(user: User, name: str) -> None:
    AthleteProfile.objects.update_or_create(owner=user, defaults={"timezone": name})


def log(user: User, job: Job, outcome: Outcome, week: date | None, at: datetime) -> JobRun:
    code = "" if outcome == Outcome.DONE else Code.UNEXPECTED
    run = record(user, job, outcome, code, week_start=week)
    JobRun.objects.filter(pk=run.pk).update(started_at=at, finished_at=at)
    return run


class TestDue:
    def test_sunday_evening_is_review_draft_and_a_sync_for_the_draft(self) -> None:
        user = make_user("a@example.com")
        zone(user, "Europe/Berlin")
        log(user, Job.SYNC, Outcome.DONE, None, SUNDAY - timedelta(minutes=5))

        assert schedule.due(user, SUNDAY) == (Job.SYNC, Job.WEEK_REVIEW, Job.WEEK_DRAFT)

    def test_before_the_hour_only_the_sync_can_be_due(self) -> None:
        user = make_user("a@example.com")
        zone(user, "Europe/Berlin")
        early = SUNDAY.replace(hour=16, minute=30)  # 17:30 in Berlin

        assert schedule.due(user, early) == (Job.SYNC,)
        log(user, Job.SYNC, Outcome.DONE, None, early - timedelta(hours=1))
        assert schedule.due(user, early) == ()

    def test_the_time_zone_of_the_user_decides(self) -> None:
        berlin = make_user("berlin@example.com")
        auckland = make_user("auckland@example.com")
        zone(berlin, "Europe/Berlin")
        zone(auckland, "Pacific/Auckland")
        # 17:30 UTC is Monday 06:30 in Auckland: that Sunday is over there.
        for user in (berlin, auckland):
            log(user, Job.SYNC, Outcome.DONE, None, SUNDAY)

        assert schedule.due(berlin, SUNDAY) == (Job.SYNC, Job.WEEK_REVIEW, Job.WEEK_DRAFT)
        assert schedule.due(auckland, SUNDAY) == ()

    def test_monday_is_not_a_sunday_evening(self) -> None:
        user = make_user("a@example.com")
        zone(user, "Europe/Berlin")
        monday = SUNDAY + timedelta(hours=6)  # 00:30 Monday in Berlin
        log(user, Job.SYNC, Outcome.DONE, None, monday)

        assert schedule.due(user, monday) == ()

    def test_the_sync_is_due_after_the_configured_hours(self, settings: object) -> None:
        user = make_user("a@example.com")
        thursday = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)
        assert schedule.due(user, thursday) == (Job.SYNC,)
        log(user, Job.SYNC, Outcome.SKIPPED, None, thursday - timedelta(hours=5))
        assert schedule.due(user, thursday) == ()
        log(user, Job.SYNC, Outcome.FAILED, None, thursday - timedelta(hours=6))
        JobRun.objects.for_user(user).filter(outcome=Outcome.SKIPPED).delete()
        assert schedule.due(user, thursday) == (Job.SYNC,)

    def test_done_and_skipped_settle_a_week(self) -> None:
        user = make_user("a@example.com")
        zone(user, "Europe/Berlin")
        log(user, Job.SYNC, Outcome.DONE, None, SUNDAY)
        log(user, Job.WEEK_REVIEW, Outcome.SKIPPED, THIS_MONDAY, SUNDAY)
        assert schedule.due(user, SUNDAY) == (Job.SYNC, Job.WEEK_DRAFT)  # not vacuous
        log(user, Job.WEEK_DRAFT, Outcome.DONE, NEXT_MONDAY, SUNDAY)

        assert schedule.due(user, SUNDAY) == ()

    def test_a_failed_job_is_tried_again_up_to_the_cap(self) -> None:
        user = make_user("a@example.com")
        zone(user, "Europe/Berlin")
        log(user, Job.SYNC, Outcome.DONE, None, SUNDAY)
        log(user, Job.WEEK_DRAFT, Outcome.DONE, NEXT_MONDAY, SUNDAY)
        for tries in range(1, schedule.MAX_FAILED_TRIES + 1):
            assert schedule.due(user, SUNDAY) == (Job.WEEK_REVIEW,), tries
            log(user, Job.WEEK_REVIEW, Outcome.FAILED, THIS_MONDAY, SUNDAY)
        assert schedule.due(user, SUNDAY) == ()
        # The next Sunday is a new week with a fresh count.
        later = SUNDAY + timedelta(weeks=1)
        log(user, Job.SYNC, Outcome.DONE, None, later)
        assert Job.WEEK_REVIEW in schedule.due(user, later)

    def test_turned_off_jobs_are_not_due(self) -> None:
        user = make_user("a@example.com")
        zone(user, "Europe/Berlin")
        JobSettings.objects.create(owner=user, sync=False, week_review=False, week_draft=True)

        assert schedule.due(user, SUNDAY) == (Job.WEEK_DRAFT,)
        JobSettings.objects.filter(owner=user).update(week_draft=False)
        assert schedule.due(user, SUNDAY) == ()


class TestRunRound:
    @pytest.mark.parametrize(
        ("job", "name", "week"),
        [(Job.WEEK_REVIEW, "run_review", THIS_MONDAY), (Job.WEEK_DRAFT, "run_draft", NEXT_MONDAY)],
    )
    def test_an_unexpected_error_counts_toward_the_failure_cap(
        self, monkeypatch: pytest.MonkeyPatch, job: Job, name: str, week: date
    ) -> None:
        user = make_user("a@example.com")
        zone(user, "Europe/Berlin")
        log(user, Job.SYNC, Outcome.DONE, None, SUNDAY)
        other = Job.WEEK_DRAFT if job == Job.WEEK_REVIEW else Job.WEEK_REVIEW
        log(
            user,
            other,
            Outcome.DONE,
            NEXT_MONDAY if other == Job.WEEK_DRAFT else THIS_MONDAY,
            SUNDAY,
        )

        def boom(*args: object, **kwargs: object) -> None:
            raise RuntimeError("secret detail")

        monkeypatch.setattr(schedule.runner, name, boom)

        for _ in range(schedule.MAX_FAILED_TRIES):
            # A due draft brings a sync along, so only the failures are counted here.
            assert schedule.run_round(SUNDAY)[2] == 1
        assert schedule.run_round(SUNDAY) == (0, 0, 0)  # the cap holds

        failed = JobRun.objects.for_user(user).filter(job=job, outcome=Outcome.FAILED)
        assert [r.week_start for r in failed] == [week] * schedule.MAX_FAILED_TRIES
        assert {r.code for r in failed} == {Code.UNEXPECTED}


class TestSettings:
    @pytest.mark.parametrize(
        ("name", "value"),
        [
            ("JOBS_SYNC_HOURS", "0"),
            ("JOBS_SYNC_HOURS", "25"),
            ("JOBS_SUNDAY_HOUR", "24"),
            ("JOBS_SUNDAY_HOUR", "-1"),
            ("JOBS_INTERVAL_MINUTES", "0"),
            ("JOBS_INTERVAL_MINUTES", "soon"),
        ],
    )
    def test_invalid_values_stop_django(
        self, name: str, value: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Settings are read at import time, so each case starts a fresh interpreter.
        monkeypatch.setenv(name, value)
        result = subprocess.run(
            [sys.executable, "-c", "import config.settings_test"],
            cwd=Path(__file__).resolve().parents[2],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode != 0
        assert name in result.stderr


class TestRunScheduler:
    def test_one_sunday_round_serves_two_users_and_a_second_does_nothing(
        self,
        fake: FakeIntervals,  # noqa: F811
        provide: Callable[..., Scripted],  # noqa: F811
    ) -> None:
        alice = athlete("alice@example.com")
        bob = athlete("bob@example.com")
        zone(alice, "Europe/Berlin")
        zone(bob, "Europe/Berlin")
        connect(alice)
        connect(bob)
        activity_in(alice, THIS_MONDAY, 1)
        activity_in(bob, THIS_MONDAY, 2)
        # Each sync asks for activities then wellness; both users get their own wellness day.
        fake.queue(body=json.dumps([entry("a1", SUNDAY)]).encode())
        fake.queue(body=json.dumps([wellness_entry("2026-11-19", sleep_minutes=480)]).encode())
        fake.queue(body=json.dumps([entry("b1", SUNDAY)]).encode())
        fake.queue(body=json.dumps([wellness_entry("2026-11-19", sleep_minutes=360)]).encode())
        scripted = provide(
            good_comment(),
            good_plan(),
            good_plan(),
            json.dumps({"comment": "More volume.", "next_week": "increase"}),
            good_plan(),
            good_plan(),
        )

        call_command("run_scheduler", once=True, now=SUNDAY.isoformat())

        for user in (alice, bob):
            assert {r.job: r.outcome for r in JobRun.objects.for_user(user)} == {
                Job.SYNC: Outcome.DONE,
                Job.WEEK_REVIEW: Outcome.DONE,
                Job.WEEK_DRAFT: Outcome.DONE,
            }
            assert WeekComment.objects.for_user(user).count() == 1
            assert WeeklyPlan.objects.for_user(user).get().status == WeeklyPlan.Status.DRAFT
        assert [
            a.external_id for a in Activity.objects.for_user(alice).filter(source="intervals_icu")
        ] == ["a1"]
        assert [
            a.external_id for a in Activity.objects.for_user(bob).filter(source="intervals_icu")
        ] == ["b1"]
        # Each user's wellness is kept apart, even though they share the same day.
        alices = DailyWellness.objects.for_user(alice).get(day=date(2026, 11, 19))
        bobs = DailyWellness.objects.for_user(bob).get(day=date(2026, 11, 19))
        assert (alices.sleep_minutes, bobs.sleep_minutes) == (480, 360)

        # The runs were logged with the real clock; put them on the Sunday of this test.
        JobRun.objects.update(started_at=SUNDAY, finished_at=SUNDAY)
        calls, requests = len(scripted.calls), len(fake.requests)
        runs = JobRun.objects.count()
        call_command("run_scheduler", once=True, now=SUNDAY.isoformat())

        assert (len(scripted.calls), len(fake.requests), JobRun.objects.count()) == (
            calls,
            requests,
            runs,
        )

    def test_turned_off_jobs_make_no_calls(
        self,
        fake: FakeIntervals,  # noqa: F811
        provide: Callable[..., Scripted],  # noqa: F811
    ) -> None:
        user = athlete("alice@example.com")
        zone(user, "Europe/Berlin")
        connect(user)
        answer(fake)
        scripted = provide(good_comment())
        JobSettings.objects.create(owner=user, sync=False, week_review=False, week_draft=False)

        call_command("run_scheduler", once=True, now=SUNDAY.isoformat())

        assert (len(scripted.calls), len(fake.requests), JobRun.objects.count()) == (0, 0, 0)

    def test_now_must_be_a_timestamp(self) -> None:
        with pytest.raises(CommandError):
            call_command("run_scheduler", once=True, now="tomorrow")
