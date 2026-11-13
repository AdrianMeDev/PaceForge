from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from accounts.managers import clean_email
from accounts.models import User
from activities.models import Activity, ActivityFile
from activities.services import best_efforts_of
from athletes.estimates import refresh_estimates_safely


class Command(BaseCommand):
    help = (
        "Compute the best efforts of activities imported before they were computed on import, "
        "from their stored original files, then refreshes the estimated thresholds of the accounts "
        "concerned. Activities that already have them are skipped, so the command can be run "
        "again at any time. Prints counts only."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--email", help="Only the activities of this account.")

    def handle(self, *args: Any, **options: Any) -> None:
        activities = Activity.objects.filter(best_efforts__isnull=True).order_by("pk")
        if options["email"]:
            email = clean_email(options["email"])
            user = User.objects.filter(email=email).first()
            if user is None:
                raise CommandError(f"There is no account with the email {email}.")
            activities = activities.filter(owner=user)

        computed = without_series = failed = without_file = 0
        filled: set[Any] = set()
        for activity in activities.iterator(chunk_size=100):
            stored = ActivityFile.objects.filter(activity=activity).first()
            if stored is None:
                without_file += 1
                continue
            best = best_efforts_of(stored.read())
            if best is None:
                failed += 1
                continue
            Activity.objects.filter(pk=activity.pk).update(best_efforts=best)
            filled.add(activity.owner_id)
            if best:
                computed += 1
            else:
                without_series += 1

        # The estimated thresholds follow the best efforts; the next import would do it, too late.
        for user in User.objects.filter(pk__in=filled):
            refresh_estimates_safely(user)

        self.stdout.write(
            f"Computed {computed}, no usable series in {without_series}, "
            f"failed {failed}, without a stored file {without_file}."
        )
        if filled:
            self.stdout.write(f"Refreshed the estimated thresholds of {len(filled)} account(s).")
