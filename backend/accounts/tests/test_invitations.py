import hashlib
import smtplib
from datetime import timedelta
from email import message_from_string
from email.policy import default
from urllib.parse import parse_qs, urlparse

import pytest
from django.core import mail
from django.utils import timezone

from accounts.models import User, UserInvitation
from accounts.services.invitations import (
    Delivery,
    InvalidInvitationError,
    build_invitation_url,
    consume_invitation,
    create_invitation,
    get_valid_invitation,
    hash_token,
    resend_invitation,
    revoke_invitation,
    send_invitation_email,
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def public_origin(settings):
    settings.APP_ORIGIN = "https://pace.example.com"


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


def test_signup_link_carries_token_and_email() -> None:
    url = build_invitation_url(token="tok", email="a@example.com")

    parts = urlparse(url)
    assert (
        f"{parts.scheme}://{parts.netloc}{parts.path}" == "https://pace.example.com/account/signup"
    )
    assert parts.query == ""
    assert parse_qs(parts.fragment) == {"invitation": ["tok"], "email": ["a@example.com"]}


def test_signup_link_uses_the_configured_origin(settings) -> None:
    settings.APP_ORIGIN = "http://localhost:4200"

    url = build_invitation_url(token="tok", email="a@example.com")

    assert url.startswith("http://localhost:4200/account/signup#")


def test_invitation_email_is_one_mail_with_an_unescaped_link(admin: User, settings) -> None:
    created = create_invitation(invited_by=admin, email="invitee@example.com")

    assert send_invitation_email(created) == Delivery.SENT

    [message] = mail.outbox
    link = build_invitation_url(token=created.token, email="invitee@example.com")
    assert message.to == ["invitee@example.com"]
    assert message.from_email == settings.DEFAULT_FROM_EMAIL
    assert message.subject == "You are invited to PaceForge"
    assert "&" in link
    assert link in message.body
    assert "&amp;" not in message.body
    assert "invitee@example.com" not in message.subject


def test_invitation_email_says_when_the_link_expires(admin: User) -> None:
    created = create_invitation(invited_by=admin, email="invitee@example.com")

    send_invitation_email(created)

    [message] = mail.outbox
    assert "works until" in message.body
    assert "works only once" in message.body


@pytest.fixture(params=["create", "resend"])
def delivery_invitation(admin: User, request: pytest.FixtureRequest):
    created = create_invitation(invited_by=admin, email="invitee@example.com")
    if request.param == "resend":
        # A failed or console resend must preserve the previous successful send time.
        created.invitation.sent_at = timezone.now() - timedelta(days=1)
        created.invitation.save(update_fields=["sent_at"])
        return resend_invitation(created.invitation)
    return created


def test_successful_send_sets_sent_at(delivery_invitation) -> None:
    created = delivery_invitation
    previous = created.invitation.sent_at

    assert send_invitation_email(created) == Delivery.SENT

    assert created.invitation.sent_at is not None
    assert created.invitation.sent_at != previous
    sent_at = created.invitation.sent_at
    created.invitation.refresh_from_db()
    assert created.invitation.sent_at == sent_at
    assert len(mail.outbox) == 1


def test_console_send_leaves_sent_at_unchanged(
    delivery_invitation,
    settings,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    created = delivery_invitation
    previous = created.invitation.sent_at
    settings.MAILERS = {"default": {"BACKEND": "django.core.mail.backends.console.EmailBackend"}}

    assert send_invitation_email(created) == Delivery.CONSOLE

    assert created.invitation.sent_at == previous
    created.invitation.refresh_from_db()
    assert created.invitation.sent_at == previous
    output = capsys.readouterr().out
    message = message_from_string(output, policy=default)
    assert (
        build_invitation_url(token=created.token, email=created.invitation.email)
        in message.get_content()
    )
    assert mail.outbox == []
    assert created.token not in caplog.text
    assert created.invitation.email not in caplog.text


@pytest.mark.parametrize("error", [smtplib.SMTPException("refused"), OSError("connection refused")])
def test_failed_send_leaves_sent_at_unchanged(
    delivery_invitation, monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    created = delivery_invitation
    previous = created.invitation.sent_at

    def failing_send(*args, **kwargs):
        raise error

    monkeypatch.setattr("accounts.services.invitations.send_mail", failing_send)

    assert send_invitation_email(created) == Delivery.FAILED

    assert created.invitation.sent_at == previous
    created.invitation.refresh_from_db()
    assert created.invitation.sent_at == previous
    assert mail.outbox == []


def test_failed_send_logs_without_the_token_or_the_address(
    admin: User, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    created = create_invitation(invited_by=admin, email="invitee@example.com")

    def failing_send(*args, **kwargs):
        raise smtplib.SMTPRecipientsRefused({"invitee@example.com": (550, b"no such user")})

    monkeypatch.setattr("accounts.services.invitations.send_mail", failing_send)

    send_invitation_email(created)

    assert "Could not send invitation" in caplog.text
    assert "SMTPRecipientsRefused" in caplog.text
    assert created.token not in caplog.text
    assert "invitee@example.com" not in caplog.text


def test_resend_replaces_the_token_of_a_pending_invitation(admin: User) -> None:
    created = create_invitation(invited_by=admin, email="invitee@example.com")
    old_hash = created.invitation.token_hash

    resent = resend_invitation(created.invitation)

    assert resent.token != created.token
    assert resent.invitation.token_hash == hash_token(resent.token)
    assert resent.invitation.token_hash != old_hash
    assert resent.invitation.status == UserInvitation.Status.PENDING
    with pytest.raises(InvalidInvitationError):
        get_valid_invitation(created.token)
    assert get_valid_invitation(resent.token) == resent.invitation


def test_resend_extends_the_expiry_of_a_pending_invitation(admin: User) -> None:
    created = create_invitation(invited_by=admin, email="invitee@example.com")
    UserInvitation.objects.update(expires_at=timezone.now() + timedelta(hours=1))

    resent = resend_invitation(created.invitation)

    assert resent.invitation.expires_at - timezone.now() > timedelta(days=6)


def test_resend_revives_an_expired_invitation(admin: User) -> None:
    created = create_invitation(invited_by=admin, email="invitee@example.com")
    UserInvitation.objects.update(expires_at=timezone.now() - timedelta(seconds=1))

    resent = resend_invitation(created.invitation)

    assert resent.invitation.status == UserInvitation.Status.PENDING
    assert get_valid_invitation(resent.token) == resent.invitation


def test_resend_refuses_a_used_invitation(admin: User, invitee: User) -> None:
    created = create_invitation(invited_by=admin, email=invitee.email)
    consume_invitation(created.token, user=invitee)

    with pytest.raises(InvalidInvitationError):
        resend_invitation(created.invitation)

    stored = UserInvitation.objects.get(pk=created.invitation.pk)
    assert stored.token_hash == hash_token(created.token)


def test_resend_refuses_a_revoked_invitation(admin: User) -> None:
    created = create_invitation(invited_by=admin, email="invitee@example.com")
    revoke_invitation(created.invitation)

    with pytest.raises(InvalidInvitationError):
        resend_invitation(created.invitation)

    stored = UserInvitation.objects.get(pk=created.invitation.pk)
    assert stored.token_hash == hash_token(created.token)
    assert stored.revoked_at is not None
