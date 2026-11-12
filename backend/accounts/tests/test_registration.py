import os
import subprocess
import sys
from datetime import timedelta
from http import HTTPStatus
from pathlib import Path

import pytest
from django.core import mail

from accounts.models import User, UserInvitation
from accounts.services import invitations
from accounts.services.invitations import InvalidInvitationError, create_invitation

from .conftest import PASSWORD, AuthApi

pytestmark = pytest.mark.django_db

EMAIL = "invitee@example.com"


def signup(api: AuthApi, token: str | None, email: str = EMAIL, password: str = PASSWORD):
    data = {"email": email, "password": password}
    if token is not None:
        data["invitation_token"] = token
    return api.request("POST", "/auth/signup", data)


def error_codes(response) -> set[tuple[str, str]]:
    return {(error["param"], error["code"]) for error in response.json()["errors"]}


@pytest.fixture
def invitation(verified_staff: User):
    return create_invitation(invited_by=verified_staff, email=EMAIL)


def test_signup_with_valid_invitation_creates_user_and_consumes_it(
    api: AuthApi, invitation
) -> None:
    response = signup(api, invitation.token)

    # Registration succeeded; the email still has to be verified before the first login.
    assert response.status_code == HTTPStatus.UNAUTHORIZED
    assert any(flow["id"] == "verify_email" for flow in response.json()["data"]["flows"])
    user = User.objects.get(email=EMAIL)
    used = UserInvitation.objects.get(pk=invitation.invitation.pk)
    assert used.status == UserInvitation.Status.USED
    assert used.used_by == user
    assert len(mail.outbox) == 1


def test_signup_without_token_is_rejected(api: AuthApi, invitation) -> None:
    response = signup(api, None)

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert ("invitation_token", "invalid_invitation") in error_codes(response)
    assert not User.objects.filter(email=EMAIL).exists()


def test_signup_with_unknown_token_is_rejected(api: AuthApi, invitation) -> None:
    response = signup(api, "not-a-real-token")

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert not User.objects.filter(email=EMAIL).exists()


def test_signup_with_token_for_another_email_is_rejected(api: AuthApi, invitation) -> None:
    response = signup(api, invitation.token, email="someone-else@example.com")

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert not User.objects.filter(email="someone-else@example.com").exists()
    assert get_status(invitation) == UserInvitation.Status.PENDING


def test_signup_with_revoked_or_expired_invitation_is_rejected(
    api: AuthApi, verified_staff: User
) -> None:
    revoked = create_invitation(invited_by=verified_staff, email="a@example.com")
    invitations.revoke_invitation(revoked.invitation)
    expired = create_invitation(
        invited_by=verified_staff, email="b@example.com", ttl=timedelta(seconds=-1)
    )

    assert signup(api, revoked.token, email="a@example.com").status_code == 400
    assert signup(api, expired.token, email="b@example.com").status_code == 400
    assert User.objects.filter(email__in=["a@example.com", "b@example.com"]).count() == 0


def test_invitation_cannot_be_used_twice(api: AuthApi, invitation) -> None:
    assert signup(api, invitation.token).status_code == HTTPStatus.UNAUTHORIZED

    second = signup(AuthApi(), invitation.token, email=EMAIL)

    assert second.status_code == HTTPStatus.BAD_REQUEST
    assert User.objects.filter(email=EMAIL).count() == 1


def test_rejected_signup_does_not_burn_the_invitation(api: AuthApi, invitation) -> None:
    response = signup(api, invitation.token, password="123")  # too weak

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert get_status(invitation) == UserInvitation.Status.PENDING
    assert signup(api, invitation.token).status_code == HTTPStatus.UNAUTHORIZED


def test_losing_a_race_for_the_invitation_rolls_back_the_user(
    api: AuthApi, invitation, monkeypatch: pytest.MonkeyPatch
) -> None:
    def lost_race(*args, **kwargs):
        raise InvalidInvitationError

    monkeypatch.setattr("accounts.adapters.consume_invitation", lost_race)

    response = signup(api, invitation.token)

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert ("invitation_token", "invalid_invitation") in error_codes(response)
    assert not User.objects.filter(email=EMAIL).exists()


def test_closed_registration_ignores_valid_invitations(api: AuthApi, invitation, settings) -> None:
    settings.REGISTRATION_MODE = "closed"

    assert signup(api, invitation.token).status_code == HTTPStatus.FORBIDDEN
    assert not User.objects.filter(email=EMAIL).exists()


def test_open_registration_needs_no_invitation(api: AuthApi, settings) -> None:
    settings.REGISTRATION_MODE = "open"

    response = signup(api, None, email="walkin@example.com")

    assert response.status_code == HTTPStatus.UNAUTHORIZED
    assert User.objects.filter(email="walkin@example.com").exists()


def test_invalid_registration_mode_fails_at_startup() -> None:
    env = os.environ | {
        "DJANGO_SECRET_KEY": "x",
        "DATABASE_URL": "sqlite:///unused.db",
        "REGISTRATION_MODE": "everyone",
    }

    result = subprocess.run(
        [sys.executable, "-c", "import config.settings"],
        env=env,
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "Invalid REGISTRATION_MODE" in result.stderr


def get_status(created) -> UserInvitation.Status:
    return UserInvitation.objects.get(pk=created.invitation.pk).status


def test_default_mode_is_invite_only(settings) -> None:
    assert settings.REGISTRATION_MODE == "invite_only"


def test_signup_with_an_address_that_already_has_an_account_answers_like_a_new_signup(
    api: AuthApi, verified_staff: User, verified_user: User
) -> None:
    invitation = create_invitation(invited_by=verified_staff, email=verified_user.email)
    password_hash = verified_user.password

    response = signup(
        api, invitation.token, email=verified_user.email, password="another-long-pw-1"
    )

    assert response.status_code == HTTPStatus.UNAUTHORIZED
    assert [f["id"] for f in response.json()["data"]["flows"] if f.get("is_pending")] == [
        "verify_email"
    ]
    verified_user.refresh_from_db()
    assert verified_user.password == password_hash


def test_the_owner_of_an_existing_address_is_pointed_to_the_password_reset(
    api: AuthApi, verified_staff: User, verified_user: User
) -> None:
    invitation = create_invitation(invited_by=verified_staff, email=verified_user.email)

    signup(api, invitation.token, email=verified_user.email)

    [message] = mail.outbox
    assert message.to == [verified_user.email]
    assert "http://testserver/account/password/reset\n" in message.body
    assert "/account/password/reset/key/" not in message.body
