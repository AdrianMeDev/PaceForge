from datetime import date

import pytest
from django.contrib.auth.models import AnonymousUser
from django.db import IntegrityError, transaction

from accounts.models import User
from jobs.models import Code, Job, JobRun, JobSettings, Outcome
from jobs.services import is_allowed, record, runs_of, settings_of

pytestmark = pytest.mark.django_db

MONDAY = date(2027, 7, 12)
assert MONDAY.weekday() == 0


@pytest.fixture
def alice() -> User:
    return User.objects.create_user("alice@example.com")


@pytest.fixture
def bob() -> User:
    return User.objects.create_user("bob@example.com")


def test_a_user_without_a_row_has_every_job_on(alice: User) -> None:
    settings = settings_of(alice)

    assert settings.sync is True
    assert settings.week_review is True
    assert settings.week_draft is True
    assert all(is_allowed(alice, job) for job in Job)
    # Reading the defaults writes nothing.
    assert not JobSettings.objects.exists()


def test_reading_the_settings_twice_does_not_create_a_row(alice: User) -> None:
    settings_of(alice)
    settings_of(alice)

    assert JobSettings.objects.for_user(alice).count() == 0


def test_a_stored_row_is_read_back(alice: User) -> None:
    JobSettings.objects.create(owner=alice, week_draft=False)

    assert is_allowed(alice, Job.SYNC) is True
    assert is_allowed(alice, Job.WEEK_REVIEW) is True
    assert is_allowed(alice, Job.WEEK_DRAFT) is False


def test_a_user_has_one_row_of_settings(alice: User) -> None:
    JobSettings.objects.create(owner=alice)

    with pytest.raises(IntegrityError), transaction.atomic():
        JobSettings.objects.create(owner=alice)


def test_each_user_keeps_their_own_settings(alice: User, bob: User) -> None:
    JobSettings.objects.create(owner=alice, sync=False)

    assert settings_of(bob).sync is True
    assert list(JobSettings.objects.for_user(bob)) == []


def test_record_writes_only_the_given_owner(alice: User, bob: User) -> None:
    run = record(
        alice,
        Job.SYNC,
        Outcome.DONE,
        counts={"new_activities": 3},
    )

    assert run.owner_id == alice.pk
    assert run.code == ""
    assert run.counts == {"new_activities": 3}
    assert run.week_start is None
    assert list(JobRun.objects.for_user(alice)) == [run]
    assert list(JobRun.objects.for_user(bob)) == []


def test_record_keeps_the_job_the_outcome_the_code_and_the_week(alice: User) -> None:
    run = record(
        alice,
        Job.WEEK_DRAFT,
        Outcome.SKIPPED,
        Code.ALREADY_PLANNED,
        week_start=MONDAY,
    )

    assert (run.job, run.outcome, run.code, run.week_start) == (
        Job.WEEK_DRAFT,
        Outcome.SKIPPED,
        Code.ALREADY_PLANNED,
        MONDAY,
    )
    assert run.counts == {}


def test_for_user_hides_the_runs_of_other_users(alice: User, bob: User) -> None:
    mine = record(alice, Job.SYNC, Outcome.DONE)
    theirs = record(bob, Job.SYNC, Outcome.FAILED, Code.INVALID_KEY)

    assert list(JobRun.objects.for_user(alice)) == [mine]
    assert list(JobRun.objects.for_user(bob)) == [theirs]
    assert runs_of(alice) == [mine]
    assert runs_of(bob) == [theirs]


def test_an_anonymous_user_owns_no_run(alice: User) -> None:
    record(alice, Job.SYNC, Outcome.DONE)

    assert list(JobRun.objects.for_user(AnonymousUser())) == []


def test_runs_of_one_job_only(alice: User) -> None:
    sync = record(alice, Job.SYNC, Outcome.DONE)
    record(alice, Job.WEEK_REVIEW, Outcome.SKIPPED, Code.NOTHING_TO_REVIEW)

    assert runs_of(alice, Job.SYNC) == [sync]
    assert [run.job for run in runs_of(alice)] == [Job.WEEK_REVIEW, Job.SYNC]


def test_a_run_that_did_not_succeed_needs_a_code(alice: User) -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        JobRun.objects.create(owner=alice, job=Job.SYNC, outcome=Outcome.FAILED, code="")


def test_a_week_run_starts_on_a_monday(alice: User) -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        JobRun.objects.create(
            owner=alice,
            job=Job.WEEK_REVIEW,
            outcome=Outcome.DONE,
            week_start=date(2027, 7, 13),
        )


def test_the_str_of_a_run_names_no_personal_data(alice: User) -> None:
    run = record(alice, Job.SYNC, Outcome.FAILED, Code.INTERVALS_UNAVAILABLE)

    assert alice.email not in str(run)
    assert str(run).startswith("sync run of user")
