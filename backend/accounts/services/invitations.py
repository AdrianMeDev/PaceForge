import hashlib
import secrets
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from accounts.managers import clean_email
from accounts.models import User, UserInvitation


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
