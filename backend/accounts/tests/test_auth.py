from http import HTTPStatus

import pytest
from allauth.account.models import EmailAddress
from django.core import mail
from django.test import Client

from accounts.models import User

from .conftest import AUTH_API, PASSWORD, AuthApi, key_from_last_mail

pytestmark = pytest.mark.django_db


def test_state_changing_requests_require_csrf_token(verified_user: User) -> None:
    api = AuthApi()
    api._csrf_token()
    del api.client.cookies["csrftoken"]  # a request without the token

    response = api.client.post(
        f"{AUTH_API}/auth/login",
        {"email": verified_user.email, "password": PASSWORD},
        content_type="application/json",
    )

    assert response.status_code == HTTPStatus.FORBIDDEN


def test_login_creates_httponly_session_cookie(api: AuthApi, verified_user: User) -> None:
    response = api.login(verified_user.email)

    assert response.status_code == HTTPStatus.OK
    assert response.json()["meta"]["is_authenticated"] is True
    cookie = api.client.cookies["sessionid"]
    assert cookie["httponly"]
    assert cookie["samesite"] == "Lax"
    # No tokens are handed to the browser besides the cookie-bound session.
    assert "access_token" not in response.json()["meta"]
    assert "session_token" not in response.json()["meta"]
    assert api.is_authenticated


def test_login_with_wrong_password_fails(api: AuthApi, verified_user: User) -> None:
    response = api.login(verified_user.email, "wrong-password")

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert not api.is_authenticated


def test_logout_ends_the_session(api: AuthApi, verified_user: User) -> None:
    api.login(verified_user.email)

    response = api.request("DELETE", "/auth/session")

    assert response.status_code == HTTPStatus.UNAUTHORIZED
    assert not api.is_authenticated


def test_repeated_failed_logins_are_rate_limited(api: AuthApi, verified_user: User) -> None:
    for _ in range(5):
        api.login(verified_user.email, "wrong-password")

    # allauth reports the lockout as a validation error, not as HTTP 429.
    for password in ("wrong-password", PASSWORD):
        response = api.login(verified_user.email, password)
        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert response.json()["errors"][0]["code"] == "too_many_login_attempts"
    assert not api.is_authenticated


def test_login_requires_verified_email(api: AuthApi) -> None:
    User.objects.create_user("new@example.com", PASSWORD)

    response = api.login("new@example.com")

    assert response.status_code == HTTPStatus.UNAUTHORIZED
    assert any(flow["id"] == "verify_email" for flow in response.json()["data"]["flows"])
    assert not api.is_authenticated
    assert len(mail.outbox) == 1


def test_email_verification_unlocks_login(api: AuthApi) -> None:
    user = User.objects.create_user("new@example.com", PASSWORD)
    api.login("new@example.com")
    key = key_from_last_mail("/account/verify-email")

    response = api.request("POST", "/auth/email/verify", {"key": key})

    # Verifying does not log the user in; they sign in afterwards.
    assert response.status_code == HTTPStatus.UNAUTHORIZED
    assert EmailAddress.objects.get(user=user).verified
    assert api.login("new@example.com").status_code == HTTPStatus.OK
    assert api.is_authenticated


def test_password_reset_flow(api: AuthApi, verified_user: User) -> None:
    response = api.request("POST", "/auth/password/request", {"email": verified_user.email})
    assert response.status_code == HTTPStatus.OK
    key = key_from_last_mail("/account/password/reset/key")

    new_password = "an-entirely-different-passphrase"
    response = api.request("POST", "/auth/password/reset", {"key": key, "password": new_password})

    assert response.status_code in {HTTPStatus.OK, HTTPStatus.UNAUTHORIZED}
    assert api.login(verified_user.email, PASSWORD).status_code == HTTPStatus.BAD_REQUEST
    assert api.login(verified_user.email, new_password).status_code == HTTPStatus.OK


def test_password_reset_does_not_reveal_unknown_emails(api: AuthApi) -> None:
    response = api.request("POST", "/auth/password/request", {"email": "nobody@example.com"})

    assert response.status_code == HTTPStatus.OK
    # The response is identical to the known-account case; at most a notice without a reset link.
    assert all("/password/reset/key/" not in message.body for message in mail.outbox)


def test_signup_is_refused_when_registration_is_closed(api: AuthApi, settings) -> None:
    settings.REGISTRATION_MODE = "closed"

    response = api.request(
        "POST", "/auth/signup", {"email": "intruder@example.com", "password": PASSWORD}
    )

    assert response.status_code == HTTPStatus.FORBIDDEN
    assert not User.objects.filter(email="intruder@example.com").exists()


def test_token_based_app_client_is_not_exposed(client: Client) -> None:
    assert client.get("/api/auth/app/v1/config").status_code == HTTPStatus.NOT_FOUND
