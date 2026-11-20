"""Deleting an account together with everything stored about it.

``delete_account`` checks the typed email, the password and, when an authenticator app is set
up, a second factor. The last active administrator cannot be removed, or nobody could manage
the instance anymore. Deleting the user row removes every personal record through the cascade;
nothing is sent to Intervals.icu or an AI provider.
"""

from allauth.mfa.models import Authenticator
from django.contrib.sessions.models import Session
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from accounts.models import User, UserInvitation
from accounts.services.mfa import has_totp


class AccountDeletionError(Exception):
    """Base class of every reason an account cannot be deleted."""


class ConfirmationMismatchError(AccountDeletionError):
    """The typed email is not the email of the account."""


class InvalidPasswordError(AccountDeletionError):
    """The password is wrong."""


class MfaRequiredError(AccountDeletionError):
    """The account has an authenticator app and no code was given."""


class InvalidMfaCodeError(AccountDeletionError):
    """The code is neither a valid authenticator code nor an unused recovery code."""


class LastAdminError(AccountDeletionError):
    """The account is the last active administrator."""


def verify_mfa_code(user: User, code: str) -> bool:
    """Whether ``code`` is a current authenticator code or an unused recovery code of ``user``.

    A recovery code that matches is used up, like at sign-in.
    """
    code = "".join(code.split())
    if not code:
        return False
    authenticators = Authenticator.objects.filter(
        user=user,
        type__in=[Authenticator.Type.TOTP, Authenticator.Type.RECOVERY_CODES],
    ).order_by("type")
    return any(authenticator.wrap().validate_code(code) for authenticator in authenticators)


def _delete_sessions(user: User) -> None:
    """Ends every active session of ``user``. Sessions only hold the user id in their data."""
    expected = str(user.pk)
    for session in Session.objects.filter(expire_date__gt=timezone.now()).iterator():
        if session.get_decoded().get("_auth_user_id") == expected:
            session.delete()


def delete_account(user: User, *, password: str, confirmation: str, mfa_code: str = "") -> None:
    """Deletes ``user`` and all their data, or raises an ``AccountDeletionError``."""
    if confirmation.strip().casefold() != user.email.casefold():
        raise ConfirmationMismatchError
    if not user.check_password(password):
        raise InvalidPasswordError

    with transaction.atomic():
        if has_totp(user):
            if not mfa_code.strip():
                raise MfaRequiredError
            if not verify_mfa_code(user, mfa_code):
                raise InvalidMfaCodeError

        # Lock all active administrators in a fixed order, so two admins deleting themselves
        # at the same moment cannot both pass the check.
        admins = list(
            User.objects.select_for_update()
            .filter(is_staff=True, is_active=True)
            .order_by("pk")
            .values_list("pk", flat=True)
        )
        if admins == [user.pk]:
            raise LastAdminError

        UserInvitation.objects.filter(Q(used_by=user) | Q(email__iexact=user.email)).delete()
        _delete_sessions(user)
        user.delete()
