import smtplib
import uuid
from datetime import timedelta
from http import HTTPStatus
from urllib.parse import parse_qs, urlparse

import pytest
from django.core import mail
from django.core.cache import cache

from accounts.models import InvitationEmailCounter, User, UserInvitation
from accounts.services.invitations import consume_invitation, create_invitation

from .conftest import PASSWORD, AuthApi, enable_totp

pytestmark = pytest.mark.django_db

URL = "/api/admin/invitations/"


@pytest.fixture
def staff_api(api: AuthApi, verified_staff: User) -> AuthApi:
    """Signed in as an administrator with two-factor authentication, as the API requires."""
    factor = enable_totp(verified_staff)
    assert api.login_with_totp(verified_staff.email, factor.secret).status_code == HTTPStatus.OK
    return api


@pytest.fixture
def member_api(api: AuthApi, verified_user: User) -> AuthApi:
    assert api.login(verified_user.email).status_code == HTTPStatus.OK
    return api


def test_anonymous_users_are_refused(api: AuthApi) -> None:
    assert api.call("GET", URL).status_code == HTTPStatus.FORBIDDEN
    assert api.call("POST", URL, {"email": "a@example.com"}).status_code == HTTPStatus.FORBIDDEN


def test_non_staff_users_are_refused(member_api: AuthApi, verified_staff: User) -> None:
    created = create_invitation(invited_by=verified_staff, email="a@example.com")

    assert member_api.call("GET", URL).status_code == HTTPStatus.FORBIDDEN
    assert member_api.call("POST", URL, {"email": "b@example.com"}).status_code == 403
    revoke = f"{URL}{created.invitation.pk}/revoke/"
    assert member_api.call("POST", revoke).status_code == HTTPStatus.FORBIDDEN
    assert UserInvitation.objects.get(pk=created.invitation.pk).revoked_at is None


def test_staff_creates_invitation_and_gets_a_link_once(staff_api: AuthApi) -> None:
    response = staff_api.call("POST", URL, {"email": "Invitee@Example.com"})

    assert response.status_code == HTTPStatus.CREATED
    body = response.json()
    assert body["email"] == "invitee@example.com"
    assert body["status"] == "pending"
    link = urlparse(body["invite_url"])
    assert link.path == "/account/signup"
    query = parse_qs(link.query)
    assert set(query) == {"invitation", "email"}
    assert query["email"] == ["invitee@example.com"]  # normalised like the stored address
    token = query["invitation"][0]
    stored = UserInvitation.objects.get(pk=body["id"])
    assert stored.token_hash != token
    assert stored.invited_by is not None
    assert stored.invited_by.email == "admin@example.com"


def test_link_from_the_api_works_for_signup(staff_api: AuthApi) -> None:
    body = staff_api.call("POST", URL, {"email": "invitee@example.com"}).json()
    token = parse_qs(urlparse(body["invite_url"]).query)["invitation"][0]

    response = AuthApi().request(
        "POST",
        "/auth/signup",
        {"email": "invitee@example.com", "password": PASSWORD, "invitation_token": token},
    )

    assert response.status_code == HTTPStatus.UNAUTHORIZED  # email verification pending
    assert User.objects.filter(email="invitee@example.com").exists()


def test_link_keeps_special_characters_of_the_email_intact(staff_api: AuthApi) -> None:
    body = staff_api.call("POST", URL, {"email": "ann+running@example.com"}).json()

    query = parse_qs(urlparse(body["invite_url"]).query)

    # `+` must be percent-encoded, otherwise the signup page would read a space.
    assert query["email"] == ["ann+running@example.com"]
    assert "%2B" in body["invite_url"]


def test_list_never_exposes_tokens_or_hashes(staff_api: AuthApi, verified_staff: User) -> None:
    created = create_invitation(invited_by=verified_staff, email="a@example.com")

    response = staff_api.call("GET", URL)

    assert response.status_code == HTTPStatus.OK
    [item] = response.json()
    assert set(item) == {"id", "email", "status", "created_at", "expires_at", "sent_at"}
    assert created.token not in response.content.decode()
    assert created.invitation.token_hash not in response.content.decode()


def test_create_rejects_invalid_email(staff_api: AuthApi) -> None:
    response = staff_api.call("POST", URL, {"email": "not-an-email"})

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert UserInvitation.objects.count() == 0
    assert not InvitationEmailCounter.objects.exists()


def test_create_requires_csrf_token(staff_api: AuthApi) -> None:
    # Authenticated by session cookie, but without the X-CSRFToken header.
    response = staff_api.client.post(
        URL, {"email": "a@example.com"}, content_type="application/json"
    )

    assert response.status_code == HTTPStatus.FORBIDDEN
    assert UserInvitation.objects.count() == 0


def test_staff_can_revoke_a_pending_invitation(staff_api: AuthApi, verified_staff: User) -> None:
    created = create_invitation(invited_by=verified_staff, email="a@example.com")

    response = staff_api.call("POST", f"{URL}{created.invitation.pk}/revoke/")

    assert response.status_code == HTTPStatus.OK
    assert response.json()["status"] == "revoked"
    attempt = AuthApi().request(
        "POST",
        "/auth/signup",
        {"email": "a@example.com", "password": PASSWORD, "invitation_token": created.token},
    )
    assert attempt.status_code == HTTPStatus.BAD_REQUEST


def test_used_invitation_cannot_be_revoked(staff_api: AuthApi, verified_staff: User) -> None:
    created = create_invitation(invited_by=verified_staff, email="a@example.com")
    invitee = User.objects.create_user("a@example.com")
    consume_invitation(created.token, user=invitee)

    response = staff_api.call("POST", f"{URL}{created.invitation.pk}/revoke/")

    assert response.status_code == HTTPStatus.CONFLICT


def test_revoking_unknown_invitation_returns_404(staff_api: AuthApi) -> None:
    response = staff_api.call("POST", f"{URL}{uuid.uuid4()}/revoke/")

    assert response.status_code == HTTPStatus.NOT_FOUND


def token_of(url: str) -> str:
    return parse_qs(urlparse(url).query)["invitation"][0]


def signup(token: str, email: str = "invitee@example.com") -> int:
    response = AuthApi().request(
        "POST",
        "/auth/signup",
        {"email": email, "password": PASSWORD, "invitation_token": token},
    )
    return response.status_code


def test_create_sends_one_email_with_a_working_link(staff_api: AuthApi) -> None:
    response = staff_api.call("POST", URL, {"email": "invitee@example.com"})

    body = response.json()
    assert body["email_sent"] is True
    assert body["sent_at"] is not None
    [message] = mail.outbox
    assert message.to == ["invitee@example.com"]
    assert body["invite_url"] in message.body
    assert signup(token_of(body["invite_url"])) == HTTPStatus.UNAUTHORIZED
    assert User.objects.filter(email="invitee@example.com").exists()


def test_create_survives_an_smtp_failure(
    staff_api: AuthApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    def failing_send(*args, **kwargs):
        raise smtplib.SMTPException("refused")

    monkeypatch.setattr("accounts.services.invitations.send_mail", failing_send)

    response = staff_api.call("POST", URL, {"email": "invitee@example.com"})

    assert response.status_code == HTTPStatus.CREATED
    body = response.json()
    assert body["email_sent"] is False
    assert body["sent_at"] is None
    assert mail.outbox == []
    # The link still works, so the admin can hand it on.
    assert signup(token_of(body["invite_url"])) == HTTPStatus.UNAUTHORIZED


def test_resend_rotates_the_link_of_a_pending_invitation(
    staff_api: AuthApi, verified_staff: User
) -> None:
    created = create_invitation(invited_by=verified_staff, email="invitee@example.com")

    response = staff_api.call("POST", f"{URL}{created.invitation.pk}/resend/")

    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body["email_sent"] is True
    assert body["status"] == "pending"
    assert body["sent_at"] is not None
    [message] = mail.outbox
    assert body["invite_url"] in message.body
    new_token = token_of(body["invite_url"])
    assert new_token != created.token
    assert signup(created.token) == HTTPStatus.BAD_REQUEST
    assert signup(new_token) == HTTPStatus.UNAUTHORIZED


def test_resend_revives_an_expired_invitation(staff_api: AuthApi, verified_staff: User) -> None:
    created = create_invitation(
        invited_by=verified_staff, email="invitee@example.com", ttl=timedelta(days=-1)
    )
    assert created.invitation.status == "expired"

    response = staff_api.call("POST", f"{URL}{created.invitation.pk}/resend/")

    assert response.status_code == HTTPStatus.OK
    assert response.json()["status"] == "pending"
    assert len(mail.outbox) == 1
    assert signup(created.token) == HTTPStatus.BAD_REQUEST
    assert signup(token_of(response.json()["invite_url"])) == HTTPStatus.UNAUTHORIZED


def test_resend_reports_an_smtp_failure(
    staff_api: AuthApi, verified_staff: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    created = create_invitation(invited_by=verified_staff, email="invitee@example.com")

    def failing_send(*args, **kwargs):
        raise OSError("connection refused")

    monkeypatch.setattr("accounts.services.invitations.send_mail", failing_send)

    response = staff_api.call("POST", f"{URL}{created.invitation.pk}/resend/")

    assert response.status_code == HTTPStatus.OK
    assert response.json()["email_sent"] is False
    assert signup(token_of(response.json()["invite_url"])) == HTTPStatus.UNAUTHORIZED


def test_resend_refuses_used_and_revoked_invitations(
    staff_api: AuthApi, verified_staff: User
) -> None:
    used = create_invitation(invited_by=verified_staff, email="used@example.com")
    consume_invitation(used.token, user=User.objects.create_user("used@example.com"))
    revoked = create_invitation(invited_by=verified_staff, email="revoked@example.com")
    staff_api.call("POST", f"{URL}{revoked.invitation.pk}/revoke/")

    for invitation in (used.invitation, revoked.invitation):
        response = staff_api.call("POST", f"{URL}{invitation.pk}/resend/")
        assert response.status_code == HTTPStatus.CONFLICT

    assert mail.outbox == []
    assert signup(revoked.token, "revoked@example.com") == HTTPStatus.BAD_REQUEST


def test_resending_unknown_invitation_returns_404(staff_api: AuthApi) -> None:
    response = staff_api.call("POST", f"{URL}{uuid.uuid4()}/resend/")

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert not InvitationEmailCounter.objects.exists()
    assert mail.outbox == []


def test_resend_is_refused_for_anonymous_and_non_staff(
    api: AuthApi, verified_staff: User, verified_user: User
) -> None:
    created = create_invitation(invited_by=verified_staff, email="a@example.com")
    resend = f"{URL}{created.invitation.pk}/resend/"
    assert api.call("POST", resend).status_code == HTTPStatus.FORBIDDEN

    assert api.login(verified_user.email).status_code == HTTPStatus.OK
    assert api.call("POST", resend).status_code == HTTPStatus.FORBIDDEN

    assert mail.outbox == []
    assert UserInvitation.objects.get(pk=created.invitation.pk).token_hash == (
        created.invitation.token_hash
    )


def test_resend_is_refused_for_staff_without_mfa(api: AuthApi, verified_staff: User) -> None:
    created = create_invitation(invited_by=verified_staff, email="a@example.com")
    assert api.login(verified_staff.email).status_code == HTTPStatus.OK

    response = api.call("POST", f"{URL}{created.invitation.pk}/resend/")

    assert response.status_code == HTTPStatus.FORBIDDEN
    assert mail.outbox == []


def test_resend_requires_csrf_token(staff_api: AuthApi, verified_staff: User) -> None:
    created = create_invitation(invited_by=verified_staff, email="a@example.com")

    response = staff_api.client.post(
        f"{URL}{created.invitation.pk}/resend/", content_type="application/json"
    )

    assert response.status_code == HTTPStatus.FORBIDDEN
    assert mail.outbox == []


def assert_limited_without_changes(api: AuthApi, resend: str, *, window_seconds: int) -> None:
    before = list(UserInvitation.objects.order_by("pk").values())
    mail_count = len(mail.outbox)
    for url, data in ((URL, {"email": "INVITEE@Example.com"}), (resend, None)):
        response = api.call("POST", url, data)
        assert response.status_code == HTTPStatus.TOO_MANY_REQUESTS
        assert 0 < int(response.headers["Retry-After"]) <= window_seconds
        assert list(UserInvitation.objects.order_by("pk").values()) == before
        assert len(mail.outbox) == mail_count
    # Reading invitations remains available even after both rejected requests.
    for _ in range(21):
        assert api.call("GET", URL).status_code == HTTPStatus.OK


def test_creates_and_resends_share_the_sender_limit(staff_api: AuthApi) -> None:
    # Ten creates and ten resends use the same administrator's twenty reservations.
    for i in range(10):
        response = staff_api.call("POST", URL, {"email": f"user{i}@example.com"})
        assert response.status_code == HTTPStatus.CREATED
        resend = f"{URL}{response.json()['id']}/resend/"
        assert staff_api.call("POST", resend).status_code == HTTPStatus.OK
    assert len(mail.outbox) == 20

    # A process cache reset cannot clear the shared database counters.
    cache.clear()
    assert_limited_without_changes(staff_api, resend, window_seconds=60)


def test_recipient_limit_spans_administrators_and_address_case(
    staff_api: AuthApi, verified_user: User
) -> None:
    response = staff_api.call("POST", URL, {"email": "Invitee@Example.com"})
    assert response.status_code == HTTPStatus.CREATED
    resend = f"{URL}{response.json()['id']}/resend/"
    for _ in range(4):
        assert staff_api.call("POST", resend).status_code == HTTPStatus.OK
    assert len(mail.outbox) == 5

    verified_user.is_staff = True
    verified_user.save(update_fields=["is_staff"])
    factor = enable_totp(verified_user)
    second_admin = AuthApi()
    assert (
        second_admin.login_with_totp(verified_user.email, factor.secret).status_code
        == HTTPStatus.OK
    )
    cache.clear()
    # Both a differently cased create and a resend of the stored address hit the same limit.
    assert_limited_without_changes(second_admin, resend, window_seconds=3600)
    # The refusal did not exhaust the second administrator's own limit.
    assert second_admin.call("POST", URL, {"email": "other@example.com"}).status_code == (
        HTTPStatus.CREATED
    )
