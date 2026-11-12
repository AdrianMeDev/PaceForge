import uuid
from http import HTTPStatus
from urllib.parse import parse_qs, urlparse

import pytest

from accounts.models import User, UserInvitation
from accounts.services.invitations import consume_invitation, create_invitation

from .conftest import PASSWORD, AuthApi

pytestmark = pytest.mark.django_db

URL = "/api/admin/invitations/"


@pytest.fixture
def staff_api(api: AuthApi, verified_staff: User) -> AuthApi:
    assert api.login(verified_staff.email).status_code == HTTPStatus.OK
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
    token = parse_qs(link.query)["invitation"][0]
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


def test_list_never_exposes_tokens_or_hashes(staff_api: AuthApi, verified_staff: User) -> None:
    created = create_invitation(invited_by=verified_staff, email="a@example.com")

    response = staff_api.call("GET", URL)

    assert response.status_code == HTTPStatus.OK
    [item] = response.json()
    assert set(item) == {"id", "email", "status", "created_at", "expires_at"}
    assert created.token not in response.content.decode()
    assert created.invitation.token_hash not in response.content.decode()


def test_create_rejects_invalid_email(staff_api: AuthApi) -> None:
    response = staff_api.call("POST", URL, {"email": "not-an-email"})

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert UserInvitation.objects.count() == 0


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
