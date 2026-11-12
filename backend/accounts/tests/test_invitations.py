import hashlib
from datetime import timedelta

import pytest
from django.utils import timezone

from accounts.models import User, UserInvitation
from accounts.services.invitations import (
    InvalidInvitationError,
    consume_invitation,
    create_invitation,
    get_valid_invitation,
    revoke_invitation,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin() -> User:
    return User.objects.create_superuser("admin@example.com", "s3cure-passphrase")


@pytest.fixture
def invitee() -> User:
    return User.objects.create_user("invitee@example.com")


def test_create_invitation_stores_only_the_token_hash(admin: User) -> None:
    created = create_invitation(invited_by=admin, email=" Invitee@Example.com ")

    invitation = created.invitation
    assert invitation.email == "invitee@example.com"
    assert invitation.invited_by == admin
    assert invitation.status == UserInvitation.Status.PENDING
    assert invitation.token_hash == hashlib.sha256(created.token.encode()).hexdigest()
    stored = UserInvitation.objects.values().get(pk=invitation.pk)
    assert created.token not in {str(value) for value in stored.values()}


def test_valid_token_is_found(admin: User) -> None:
    created = create_invitation(invited_by=admin, email="invitee@example.com")

    assert get_valid_invitation(created.token) == created.invitation


def test_unknown_token_is_rejected() -> None:
    with pytest.raises(InvalidInvitationError):
        get_valid_invitation("not-a-real-token")


def test_expired_invitation_is_rejected(admin: User) -> None:
    created = create_invitation(invited_by=admin, email="invitee@example.com")
    UserInvitation.objects.update(expires_at=timezone.now() - timedelta(seconds=1))

    with pytest.raises(InvalidInvitationError):
        get_valid_invitation(created.token)
    created.invitation.refresh_from_db()
    assert created.invitation.status == UserInvitation.Status.EXPIRED


def test_revoked_invitation_is_rejected(admin: User) -> None:
    created = create_invitation(invited_by=admin, email="invitee@example.com")

    revoke_invitation(created.invitation)

    assert created.invitation.status == UserInvitation.Status.REVOKED
    with pytest.raises(InvalidInvitationError):
        get_valid_invitation(created.token)


def test_revoking_twice_is_a_noop(admin: User) -> None:
    created = create_invitation(invited_by=admin, email="invitee@example.com")
    revoke_invitation(created.invitation)
    first = created.invitation.revoked_at

    revoke_invitation(created.invitation)

    assert created.invitation.revoked_at == first


def test_invitation_can_be_consumed_only_once(admin: User, invitee: User) -> None:
    created = create_invitation(invited_by=admin, email=invitee.email)

    used = consume_invitation(created.token, user=invitee)

    assert used.status == UserInvitation.Status.USED
    assert used.used_by == invitee
    with pytest.raises(InvalidInvitationError):
        consume_invitation(created.token, user=invitee)
    with pytest.raises(InvalidInvitationError):
        get_valid_invitation(created.token)


def test_used_invitation_cannot_be_revoked(admin: User, invitee: User) -> None:
    created = create_invitation(invited_by=admin, email=invitee.email)
    used = consume_invitation(created.token, user=invitee)

    with pytest.raises(InvalidInvitationError):
        revoke_invitation(used)


def test_revoked_or_expired_invitation_cannot_be_consumed(admin: User, invitee: User) -> None:
    revoked = create_invitation(invited_by=admin, email=invitee.email)
    revoke_invitation(revoked.invitation)
    expired = create_invitation(invited_by=admin, email=invitee.email, ttl=timedelta(seconds=-1))

    for created in (revoked, expired):
        with pytest.raises(InvalidInvitationError):
            consume_invitation(created.token, user=invitee)


def test_invitation_is_bound_to_its_email(admin: User, invitee: User) -> None:
    created = create_invitation(invited_by=admin, email=invitee.email)

    with pytest.raises(InvalidInvitationError):
        get_valid_invitation(created.token, email="someone-else@example.com")
    with pytest.raises(InvalidInvitationError):
        consume_invitation(created.token, user=invitee, email="someone-else@example.com")

    # A failed attempt must not burn the invitation.
    assert consume_invitation(created.token, user=invitee, email="INVITEE@example.com")


def test_default_lifetime_comes_from_settings(admin: User, settings) -> None:
    settings.INVITATION_TTL_DAYS = 3

    created = create_invitation(invited_by=admin, email="invitee@example.com")

    remaining = created.invitation.expires_at - timezone.now()
    assert timedelta(days=2, hours=23) < remaining <= timedelta(days=3)
