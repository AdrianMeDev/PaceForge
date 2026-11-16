from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from accounts.managers import clean_email
from accounts.models import User
from activities.strava import ExportError, import_export

_EVERY = 100


class Command(BaseCommand):
    help = (
        "Import the activities of a Strava bulk export (the ZIP you get at Strava under Settings, "
        "My Account, Download or Delete Your Account) for one account: the recordings (FIT, TCX "
        "and GPX, also gzip-compressed) and the sessions that exist only as a line of "
        "activities.csv. Activities the account has already (from this export, another file, a "
        "sync or by hand) are skipped, so the command can be run again at any time. Prints counts "
        "only."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("archive", help="The ZIP file of the export.")
        parser.add_argument("--user", required=True, help="The email of the account to import to.")

    def handle(self, *args: Any, **options: Any) -> None:
        email = clean_email(options["user"])
        user = User.objects.filter(email=email).first()
        if user is None:
            raise CommandError(f"There is no account with the email {email}.")

        def report(done: int, total: int) -> None:
            if done % _EVERY == 0 and done != total:
                self.stdout.write(f"{done} of {total} ...")

        try:
            counts = import_export(user, options["archive"], progress=report)
        except ExportError as error:
            raise CommandError(str(error)) from None

        self.stdout.write(
            f"Imported {counts.imported} with a recording and {counts.entered} without one. "
            f"Skipped {counts.duplicates} that you have already. "
            f"Not imported: {counts.unreadable} recordings that cannot be read, "
            f"{counts.missing} recordings that are not in the export, "
            f"{counts.lines_unreadable} lines of the list that cannot be read."
        )
