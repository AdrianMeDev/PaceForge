from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from accounts.managers import clean_email
from accounts.models import User
from activities.models import Activity, ActivityFile
from activities.services import best_efforts_of


class Command(BaseCommand):
    help = (
        "Compute the best efforts of activities imported before they were computed on import, "
        "from their stored original files. Activities that already have them are skipped, so "
        "the command can be run again at any time. Prints counts only."
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
            if best:
                computed += 1
            else:
                without_series += 1

        self.stdout.write(
            f"Computed {computed}, no usable series in {without_series}, "
            f"failed {failed}, without a stored file {without_file}."
        )
