import os
from getpass import getpass
from typing import Any

from allauth.account.models import EmailAddress
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.core.validators import validate_email
from django.db import transaction

from accounts.managers import clean_email
from accounts.models import User

PASSWORD_ENV = "SETUP_ADMIN_PASSWORD"
EMAIL_ENV = "SETUP_ADMIN_EMAIL"


class Command(BaseCommand):
    help = (
        "Create the initial administrator. Refuses to run once an administrator exists. "
        f"The password is read from ${PASSWORD_ENV} or prompted for; it is never accepted as "
        "an argument, so it does not end up in the shell history or the process list."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--email", help=f"Login email (or set ${EMAIL_ENV}).")
        parser.add_argument("--display-name", default="", help="Optional display name.")

    def handle(self, *args: Any, **options: Any) -> None:
        email = clean_email(options["email"] or os.environ.get(EMAIL_ENV))
        if not email:
            raise CommandError(f"Provide --email or set ${EMAIL_ENV}.")
        try:
            validate_email(email)
        except ValidationError:
            raise CommandError(f"'{email}' is not a valid email address.") from None

        # Fail fast, before asking for a password.
        self._ensure_setup_is_possible(email)

        password = os.environ.get(PASSWORD_ENV) or self._prompt_password()
        try:
            validate_password(password, user=User(email=email))
        except ValidationError as error:
            raise CommandError("\n".join(error.messages)) from None

        with transaction.atomic():
            self._ensure_setup_is_possible(email)  # re-check inside the transaction
            admin = User.objects.create_superuser(
                email, password, display_name=options["display_name"]
            )
            # Verification is mandatory for login; the operator owns this address by definition.
            EmailAddress.objects.create(user=admin, email=email, primary=True, verified=True)

        self.stdout.write(self.style.SUCCESS(f"Administrator {email} created."))

    def _ensure_setup_is_possible(self, email: str) -> None:
        if User.objects.filter(is_staff=True).exists():
            raise CommandError("An administrator already exists; nothing to do.")
        if User.objects.filter(email=email).exists():
            raise CommandError(f"A user with the email {email} already exists.")

    def _prompt_password(self) -> str:
        password = getpass("Password: ")
        if password != getpass("Password (again): "):
            raise CommandError("The passwords do not match.")
        return password
