"""Which jobs are due for a user, and one round that runs them.

Times are the user's own: the Sunday evening is the Sunday evening in their time zone. The sync is
due when the last attempt is ``JOBS_SYNC_HOURS`` old. The review and the draft are due on Sunday
from ``JOBS_SUNDAY_HOUR`` on, once per week: a ``done`` or ``skipped`` run for that week settles
it, and a ``failed`` one is tried again until ``MAX_FAILED_TRIES`` have failed. A job the user
turned off is never due. A due draft brings a sync with it, so it sees the latest activities.
"""

from datetime import date, datetime, timedelta

from django.conf import settings

from accounts.models import User
from goals.services import time_zone_of

from . import runner
from .models import Code, Job, JobRun, Outcome
from .services import is_allowed, record

MAX_FAILED_TRIES = 3

_SUNDAY = 6


def _local_monday(user: User, now: datetime) -> tuple[date, bool]:
    """The Monday of the week ``now`` is in, and whether it is the Sunday evening for ``user``."""
    local = now.astimezone(time_zone_of(user))
    monday = local.date() - timedelta(days=local.weekday())
    return monday, local.weekday() == _SUNDAY and local.hour >= settings.JOBS_SUNDAY_HOUR


def _week_is_open(user: User, job: Job, week_start: date) -> bool:
    """Whether ``job`` still has to run for the week: not settled, and not failed too often."""
    runs = JobRun.objects.for_user(user).filter(job=job, week_start=week_start)
    if runs.filter(outcome__in=(Outcome.DONE, Outcome.SKIPPED)).exists():
        return False
    return runs.filter(outcome=Outcome.FAILED).count() < MAX_FAILED_TRIES


def _sync_is_due(user: User, now: datetime) -> bool:
    last = JobRun.objects.for_user(user).filter(job=Job.SYNC).order_by("-started_at").first()
    return last is None or last.started_at <= now - timedelta(hours=settings.JOBS_SYNC_HOURS)


def due(user: User, now: datetime) -> tuple[Job, ...]:
    """The jobs to run for ``user`` at ``now``, in the order sync, review, draft."""
    monday, sunday_evening = _local_monday(user, now)
    review = (
        sunday_evening and is_allowed(user, Job.WEEK_REVIEW)
        and _week_is_open(user, Job.WEEK_REVIEW, monday)
    )  # fmt: skip
    draft = (
        sunday_evening and is_allowed(user, Job.WEEK_DRAFT)
        and _week_is_open(user, Job.WEEK_DRAFT, monday + timedelta(weeks=1))
    )  # fmt: skip
    sync = is_allowed(user, Job.SYNC) and (draft or _sync_is_due(user, now))
    jobs = ((Job.SYNC,) if sync else ()) + ((Job.WEEK_REVIEW,) if review else ())
    return jobs + ((Job.WEEK_DRAFT,) if draft else ())


def run_round(now: datetime) -> tuple[int, int, int]:
    """Run the due jobs of every active user, one user at a time, ordered by ``pk``.

    A job that raises becomes a ``failed/unexpected`` row and the round goes on. Returns the
    counts ``(done, skipped, failed)`` of the runs that were logged.
    """
    counts = {Outcome.DONE: 0, Outcome.SKIPPED: 0, Outcome.FAILED: 0}
    for user in User.objects.filter(is_active=True).order_by("pk"):
        monday, _ = _local_monday(user, now)
        for job in due(user, now):
            try:
                if job == Job.SYNC:
                    run = runner.run_sync(user)
                elif job == Job.WEEK_REVIEW:
                    run = runner.run_review(user, monday)
                else:
                    run = runner.run_draft(user, monday)
            except Exception:
                # An error the job did not expect; its text never reaches the log. The row
                # carries the week, or the failed tries would never count toward the cap.
                week_start = {Job.WEEK_REVIEW: monday, Job.WEEK_DRAFT: monday + timedelta(weeks=1)}
                run = record(
                    user, job, Outcome.FAILED, Code.UNEXPECTED, week_start=week_start.get(job)
                )
            if run is not None:
                counts[Outcome(run.outcome)] += 1
    return counts[Outcome.DONE], counts[Outcome.SKIPPED], counts[Outcome.FAILED]
