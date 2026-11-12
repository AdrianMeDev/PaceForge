from typing import Any

from allauth.mfa.models import Authenticator
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction

from accounts.managers import clean_email
from accounts.models import User


class Command(BaseCommand):
    help = (
        "Remove the second factor (authenticator app and recovery codes) of one account, for a "
        "user who lost both. The account keeps its password and its data and can sign in with "
        "the password alone; administrators are sent to the security page to set it up again. "
        "Existing sessions are not ended."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--email", required=True, help="Login email of the account.")

    def handle(self, *args: Any, **options: Any) -> None:
        email = clean_email(options["email"])
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise CommandError(f"There is no account with the email {email}.") from None

        with transaction.atomic():
            authenticators = Authenticator.objects.filter(user=user)
            removed = sorted(authenticators.values_list("type", flat=True))
            authenticators.delete()

        if not removed:
            self.stdout.write(f"{email} has no second factor; nothing was changed.")
            return
        self.stdout.write(
            self.style.SUCCESS(
                f"Removed the second factor of {email} ({', '.join(removed)}). "
                "They can sign in with the password alone and set it up again."
            )
        )
