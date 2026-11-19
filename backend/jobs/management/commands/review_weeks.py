"""``review_weeks``: comment on the current week of every active user.

Runs the week review job for the current week of each active account (its Monday, on the user's
own clock), ordered by ``pk``. ``--email`` limits the round to one account. The output is counts
only; no personal data, and nothing the coach said, is ever printed.
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
        "Comment on the current week of every active account. Pass --email to review one account "
        "only. Prints counts only."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--email", help="Only review this account.")

    def handle(self, *args: Any, **options: Any) -> None:
        email = clean_email(options["email"]) if options["email"] else None
        if email and not User.objects.filter(email=email, is_active=True).exists():
            raise CommandError(f"There is no active account with the email {email}.")

        def review_current_week(user: User) -> Any:
            today = today_of(user)
            monday = today - timedelta(days=today.weekday())
            return runner.run_review(user, monday)

        done, skipped, failed = runner.for_each_user(
            Job.WEEK_REVIEW, review_current_week, email=email
        )
        self.stdout.write(f"Week review: {done} done, {skipped} skipped, {failed} failed.")
