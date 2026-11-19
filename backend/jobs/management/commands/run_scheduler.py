"""``run_scheduler``: run the jobs that are due, round after round.

Each round looks at every active account (ordered by ``pk``) in its own time zone and runs what
is due: the sync every few hours, and the week review and the next week's draft on Sunday
evening. ``--once`` does one round and stops; otherwise the command sleeps ``JOBS_INTERVAL_MINUTES``
between rounds. ``--now`` sets the clock of a round (an ISO timestamp), for trying it out. The
output is counts only; no personal data is ever printed.
"""

import time
from datetime import UTC, datetime
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import close_old_connections

from jobs import schedule


def _parse_now(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        message = "--now must be an ISO timestamp, e.g. 2026-11-22T18:30:00+01:00."
        raise CommandError(message) from None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


class Command(BaseCommand):
    help = (
        "Run the background jobs that are due for every active account. Pass --once for a single "
        "round. Prints counts only."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--once", action="store_true", help="Do one round and stop.")
        parser.add_argument("--now", help="Use this ISO timestamp as the time of a round.")

    def handle(self, *args: Any, **options: Any) -> None:
        fixed = _parse_now(options["now"]) if options["now"] else None
        while True:
            done, skipped, failed = schedule.run_round(fixed or datetime.now(UTC))
            self.stdout.write(f"Scheduler: {done} done, {skipped} skipped, {failed} failed.")
            self.stdout.flush()
            if options["once"]:
                return
            # A long sleep outlives idle database connections; Django reopens what it closed.
            close_old_connections()
            time.sleep(settings.JOBS_INTERVAL_MINUTES * 60)
            close_old_connections()
