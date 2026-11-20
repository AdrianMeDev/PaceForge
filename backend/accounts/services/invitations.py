import hashlib
import logging
import secrets
import smtplib
from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import urlencode

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from accounts.managers import clean_email
from accounts.models import User, UserInvitation

logger = logging.getLogger(__name__)


class InvalidInvitationError(Exception):
    """The token is unknown, expired, revoked, already used or issued for another email."""


@dataclass(frozen=True)
class CreatedInvitation:
    invitation: UserInvitation
    # The plaintext token exists only here; it must be sent to the invitee and never stored.
    token: str


def hash_token(token: str) -> str:
    # Tokens are 256 bits of randomness, so a plain (unsalted) SHA-256 is sufficient.
    return hashlib.sha256(token.encode()).hexdigest()


def create_invitation(
    *, invited_by: User, email: str, ttl: timedelta | None = None
) -> CreatedInvitation:
    token = secrets.token_urlsafe(32)
    ttl = ttl or timedelta(days=settings.INVITATION_TTL_DAYS)
    invitation = UserInvitation.objects.create(
        email=clean_email(email),
        token_hash=hash_token(token),
        invited_by=invited_by,
        expires_at=timezone.now() + ttl,
    )
    return CreatedInvitation(invitation=invitation, token=token)


def _pending(token: str, email: str | None = None):
    """Queryset matching the invitation for ``token`` only while it is still usable."""
    invitations = UserInvitation.objects.filter(
        token_hash=hash_token(token),
        used_at__isnull=True,
        revoked_at__isnull=True,
        expires_at__gt=timezone.now(),
    )
    if email is not None:
        invitations = invitations.filter(email=clean_email(email))
    return invitations


def get_valid_invitation(token: str, *, email: str | None = None) -> UserInvitation:
    invitation = _pending(token, email).first()
    if invitation is None:
        raise InvalidInvitationError
    return invitation


def consume_invitation(token: str, *, user: User, email: str | None = None) -> UserInvitation:
    """Mark the invitation as used by ``user``. Concurrent calls cannot both succeed."""
    with transaction.atomic():
        # The conditional UPDATE is the lock: only one caller can flip `used_at` from NULL.
        updated = _pending(token, email).update(used_at=timezone.now(), used_by=user)
        if updated != 1:
            raise InvalidInvitationError
    return UserInvitation.objects.get(token_hash=hash_token(token))


def revoke_invitation(invitation: UserInvitation) -> None:
    """Revoke a pending invitation. Revoking twice is a no-op; a used one cannot be revoked."""
    if invitation.used_at is not None:
        raise InvalidInvitationError
    if invitation.revoked_at is None:
        invitation.revoked_at = timezone.now()
        invitation.save(update_fields=["revoked_at"])


def resend_invitation(
    invitation: UserInvitation, *, ttl: timedelta | None = None
) -> CreatedInvitation:
    """Issue a new token for a pending or expired invitation. The previous link stops working."""
    token = secrets.token_urlsafe(32)
    ttl = ttl or timedelta(days=settings.INVITATION_TTL_DAYS)
    # One conditional UPDATE: a used or revoked invitation is left untouched.
    updated = UserInvitation.objects.filter(
        pk=invitation.pk, used_at__isnull=True, revoked_at__isnull=True
    ).update(token_hash=hash_token(token), expires_at=timezone.now() + ttl)
    if updated != 1:
        raise InvalidInvitationError
    invitation.refresh_from_db()
    return CreatedInvitation(invitation=invitation, token=token)


def build_invitation_url(*, token: str, email: str) -> str:
    """Signup link for ``token`` on the configured public origin."""
    query = urlencode({"invitation": token, "email": email})
    signup_path = settings.HEADLESS_FRONTEND_URLS["account_signup"]
    return f"{settings.APP_ORIGIN}{signup_path}?{query}"


def send_invitation_email(created: CreatedInvitation) -> bool:
    """Mail the signup link to the invitee. Returns False if the mail could not be delivered.

    The mail carries the plaintext token, so nothing here logs the link, the token or the address.
    """
    invitation = created.invitation
    context = {
        "signup_url": build_invitation_url(token=created.token, email=invitation.email),
        "expires_at": invitation.expires_at,
    }
    subject = render_to_string("accounts/email/invitation_subject.txt", context).strip()
    body = render_to_string("accounts/email/invitation_message.txt", context)
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [invitation.email])
    except (OSError, smtplib.SMTPException) as exc:
        # The class name is enough to diagnose; the exception text may echo the address.
        logger.error("Could not send invitation %s: %s", invitation.pk, type(exc).__name__)
        return False
    invitation.sent_at = timezone.now()
    UserInvitation.objects.filter(pk=invitation.pk).update(sent_at=invitation.sent_at)
    return True
