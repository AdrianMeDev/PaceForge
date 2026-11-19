"""Reading and writing what a job needs: whether the user lets it run, and what it did.

Every function acts on the user it is given and on nothing else: a job never reads or writes
another athlete's settings or log.
"""

from collections.abc import Mapping
from datetime import date
from typing import Any

from accounts.models import User

from .models import Code, Job, JobRun, JobSettings, Outcome


def settings_of(user: User) -> JobSettings:
    """The job settings of ``user``; a user who never changed them has every job on.

    An unsaved ``JobSettings`` is returned in that case: it has the defaults of every job, and
    nothing is written just for reading them.
    """
    found = JobSettings.objects.filter(owner=user).first()
    return found if found is not None else JobSettings(owner=user)


def is_allowed(user: User, job: Job) -> bool:
    """Whether ``user`` lets ``job`` run."""
    return settings_of(user).allows(job)


def record(
    user: User,
    job: Job,
    outcome: Outcome,
    code: Code | str = "",
    *,
    week_start: date | None = None,
    counts: Mapping[str, int] | None = None,
) -> JobRun:
    """Write one attempt of ``job`` into the log of ``user`` and only there.

    ``counts`` holds small numbers only; whatever is passed is stored as it is, so callers never
    put text from the coach or from Intervals.icu in it.
    """
    return JobRun.objects.create(
        owner=user,
        job=job,
        outcome=outcome,
        code=str(code),
        week_start=week_start,
        counts=dict(counts) if counts is not None else {},
    )


def runs_of(user: User, job: Job | None = None) -> list[JobRun]:
    """The runs logged for ``user``, newest first, optionally only those of one job."""
    runs = JobRun.objects.for_user(user)
    if job is not None:
        runs = runs.filter(job=job)
    return list(runs)


def counts_or_default(counts: Any) -> dict[str, int]:
    """``counts`` as a plain dictionary, for reading a stored value back."""
    return dict(counts) if isinstance(counts, dict) else {}
