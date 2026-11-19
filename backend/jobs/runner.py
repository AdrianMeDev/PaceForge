"""Running a job for one user: every outcome becomes a log entry, never an exception.

A job that is turned off does not run at all. A provider that refuses or does not answer is a
failed attempt with a fixed code; the text of an exception never reaches the log.

The Sunday jobs take the Monday of the week that is ending. The review comments on that week,
the draft plans the week after it, and neither ever confirms a plan or pushes to Intervals.icu:
they only use the services that store a comment or a draft. A week that already has a comment or
a plan makes the job rightly do nothing, so the athlete's own work is never replaced and nothing
is paid twice.
"""

from dataclasses import asdict
from datetime import date, timedelta

from accounts.models import User
from activities.sync import sync_from_intervals
from coach import services as coach
from coach.providers.base import ProviderError
from integrations.intervals import IntervalsError, InvalidKeyError
from integrations.services import NotConnectedError
from planning.generation import NoTimeAvailable, PlanNotUsable, WeekNotPlannable, generate
from planning.models import WeeklyPlan
from reviews import commenting
from reviews.models import WeekComment

from .models import Code, Job, JobRun, Outcome
from .services import is_allowed, record


def run_sync(user: User) -> JobRun | None:
    """Import the user's activities from Intervals.icu and log how it went.

    Returns the log entry, or ``None`` when the user turned the sync job off: then nothing runs
    and nothing is logged. Every other outcome is one row with a fixed code.
    """
    if not is_allowed(user, Job.SYNC):
        return None
    try:
        counts = sync_from_intervals(user)
    except NotConnectedError:
        return record(user, Job.SYNC, Outcome.SKIPPED, Code.NOT_CONNECTED)
    except InvalidKeyError:
        return record(user, Job.SYNC, Outcome.FAILED, Code.INVALID_KEY)
    except IntervalsError:
        # Every other client error means Intervals.icu could not be read.
        return record(user, Job.SYNC, Outcome.FAILED, Code.INTERVALS_UNAVAILABLE)
    return record(user, Job.SYNC, Outcome.DONE, counts=asdict(counts))


def run_review(user: User, monday: date) -> JobRun | None:
    """Ask the coach of ``user`` to comment on the week that starts on ``monday``.

    Returns the log entry, or ``None`` when the user turned the review job off: then nothing runs
    and nothing is logged. A week that already has a comment is not asked about again. Every other
    outcome is one row with a fixed code.
    """
    if not is_allowed(user, Job.WEEK_REVIEW):
        return None
    if WeekComment.objects.for_user(user).filter(week_start=monday).exists():
        return record(
            user, Job.WEEK_REVIEW, Outcome.SKIPPED, Code.ALREADY_PLANNED, week_start=monday
        )
    try:
        commenting.comment_on(user, monday)
    except commenting.NothingToReview:
        return record(
            user, Job.WEEK_REVIEW, Outcome.SKIPPED, Code.NOTHING_TO_REVIEW, week_start=monday
        )
    except coach.NotConfiguredError:
        return record(user, Job.WEEK_REVIEW, Outcome.SKIPPED, Code.NO_COACH, week_start=monday)
    except ProviderError:
        return record(user, Job.WEEK_REVIEW, Outcome.FAILED, Code.PROVIDER_ERROR, week_start=monday)
    except commenting.CommentNotUsable:
        return record(
            user, Job.WEEK_REVIEW, Outcome.FAILED, Code.COMMENT_NOT_USABLE, week_start=monday
        )
    except Exception:
        # Anything else is an error the code did not expect, and its text never reaches the log.
        return record(user, Job.WEEK_REVIEW, Outcome.FAILED, Code.UNEXPECTED, week_start=monday)
    return record(user, Job.WEEK_REVIEW, Outcome.DONE, week_start=monday)


def run_draft(user: User, monday: date) -> JobRun | None:
    """Have the coach of ``user`` draft the week after the one that starts on ``monday``.

    Returns the log entry, or ``None`` when the user turned the draft job off: then nothing runs
    and nothing is logged. The draft is stored as a draft, whatever the rules say about it; it is
    never confirmed and nothing is pushed to Intervals.icu. A week that already has a draft or a
    confirmed plan is not drafted again. Every other outcome is one row with a fixed code.
    """
    next_monday = monday + timedelta(weeks=1)
    if not is_allowed(user, Job.WEEK_DRAFT):
        return None
    planned = WeeklyPlan.objects.for_user(user).filter(
        week_start=next_monday, status__in=(WeeklyPlan.Status.DRAFT, WeeklyPlan.Status.CONFIRMED)
    )
    if planned.exists():
        return record(
            user, Job.WEEK_DRAFT, Outcome.SKIPPED, Code.ALREADY_PLANNED, week_start=next_monday
        )
    try:
        generated = generate(user, next_monday)
    except NoTimeAvailable:
        return record(user, Job.WEEK_DRAFT, Outcome.SKIPPED, Code.NO_TIME, week_start=next_monday)
    except coach.NotConfiguredError:
        return record(user, Job.WEEK_DRAFT, Outcome.SKIPPED, Code.NO_COACH, week_start=next_monday)
    except ProviderError:
        return record(
            user, Job.WEEK_DRAFT, Outcome.FAILED, Code.PROVIDER_ERROR, week_start=next_monday
        )
    except PlanNotUsable:
        return record(
            user, Job.WEEK_DRAFT, Outcome.FAILED, Code.PLAN_NOT_USABLE, week_start=next_monday
        )
    except WeekNotPlannable:
        # The scheduler only passes weeks that can be planned, so this is not expected here.
        return record(user, Job.WEEK_DRAFT, Outcome.FAILED, Code.UNEXPECTED, week_start=next_monday)
    except Exception:
        # Anything else is an error the code did not expect, and its text never reaches the log.
        return record(user, Job.WEEK_DRAFT, Outcome.FAILED, Code.UNEXPECTED, week_start=next_monday)
    return record(
        user,
        Job.WEEK_DRAFT,
        Outcome.DONE,
        week_start=next_monday,
        counts={"errors": len(generated.report.errors)},
    )
