"""``sync_activities``: import each active user's activities from Intervals.icu.

Runs the sync job once for every active account, ordered by ``pk``, each one through its own
connection and key. ``--email`` limits the round to one account. The output is counts only; no
personal data, and nothing a provider or Intervals.icu said, is ever printed.
"""

from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from accounts.managers import clean_email
from accounts.models import User
from jobs import runner
from jobs.models import Job


class Command(BaseCommand):
    help = (
        "Sync the activities of every active account from Intervals.icu. Pass --email to sync "
        "one account only. Prints counts only."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--email", help="Only sync this account.")

    def handle(self, *args: Any, **options: Any) -> None:
        email = clean_email(options["email"]) if options["email"] else None
        if email and not User.objects.filter(email=email, is_active=True).exists():
            raise CommandError(f"There is no active account with the email {email}.")

        done, skipped, failed = runner.for_each_user(Job.SYNC, runner.run_sync, email=email)
        self.stdout.write(f"Sync: {done} done, {skipped} skipped, {failed} failed.")
