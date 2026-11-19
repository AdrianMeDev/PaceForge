"""Running a job for one user: every outcome becomes a log entry, never an exception.

A job that is turned off does not run at all. A provider that refuses or does not answer is a
failed attempt with a fixed code; the text of an exception never reaches the log.
"""

from dataclasses import asdict

from accounts.models import User
from activities.sync import sync_from_intervals
from integrations.intervals import IntervalsError, InvalidKeyError
from integrations.services import NotConnectedError

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
