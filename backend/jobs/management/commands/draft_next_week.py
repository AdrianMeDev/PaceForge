"""``draft_next_week``: sync, then draft next week for every active user.

Each active account (ordered by ``pk``) is first synced from Intervals.icu, so the draft sees the
latest activities, and then the coach drafts the week after the current one. The draft stays a
draft: it is never confirmed and nothing is pushed. ``--email`` limits the round to one account.
The output is counts only; no personal data is ever printed.
"""

from datetime import timedelta
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from accounts.managers import clean_email
from accounts.models import User
from goals.services import today_of
from jobs import runner
from jobs.models import Job


class Command(BaseCommand):
    help = (
        "Sync every active account, then have each coach draft the week after the current one. "
        "Pass --email to do one account only. Prints counts only."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--email", help="Only draft for this account.")

    def handle(self, *args: Any, **options: Any) -> None:
        email = clean_email(options["email"]) if options["email"] else None
        if email and not User.objects.filter(email=email, is_active=True).exists():
            raise CommandError(f"There is no active account with the email {email}.")

        def sync_then_draft(user: User) -> Any:
            runner.run_sync(user)  # latest activities first, so the briefing is current
            today = today_of(user)
            monday = today - timedelta(days=today.weekday())
            return runner.run_draft(user, monday)

        done, skipped, failed = runner.for_each_user(Job.WEEK_DRAFT, sync_then_draft, email=email)
        self.stdout.write(f"Draft next week: {done} done, {skipped} skipped, {failed} failed.")
