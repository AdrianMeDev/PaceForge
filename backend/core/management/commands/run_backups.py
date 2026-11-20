"""``run_backups``: make an encrypted database backup, round after round.

Each round runs ``backup_db`` with the BACKUP_* settings. ``--once`` does one round and stops
(a failure then ends the command with an error); otherwise a failed round is reported and the
command sleeps ``BACKUP_INTERVAL_HOURS`` before the next one. The interval must be a whole number
from 1 to 168; anything else fails before the first round, so a bad value cannot cause a tight
dump loop. The output is the file name, its size and the number of removed backups; no keys or
data are printed.
"""

import time
from typing import Any

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import close_old_connections


class Command(BaseCommand):
    help = (
        "Make an encrypted database backup every BACKUP_INTERVAL_HOURS hours. Pass --once for a "
        "single backup. Prints a summary only."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--once", action="store_true", help="Make one backup and stop.")

    def handle(self, *args: Any, **options: Any) -> None:
        interval = settings.BACKUP_INTERVAL_HOURS
        if isinstance(interval, bool) or not isinstance(interval, int) or not 1 <= interval <= 168:
            raise CommandError("BACKUP_INTERVAL_HOURS must be a whole number from 1 to 168.")
        while True:
            try:
                call_command("backup_db", stdout=self.stdout)
            except CommandError as error:
                if options["once"]:
                    raise
                self.stderr.write(f"Backup failed: {error}")
                self.stderr.flush()
            self.stdout.flush()
            if options["once"]:
                return
            # A long sleep outlives idle database connections; Django reopens what it closed.
            close_old_connections()
            time.sleep(settings.BACKUP_INTERVAL_HOURS * 3600)
            close_old_connections()
