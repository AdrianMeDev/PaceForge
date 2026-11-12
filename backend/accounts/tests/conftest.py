import json
import re
import time
from collections.abc import Iterator
from dataclasses import dataclass
from http import HTTPStatus
from typing import TYPE_CHECKING, Any
from urllib.parse import unquote

import pytest
from allauth.account.models import EmailAddress
from allauth.mfa import app_settings as mfa_settings
from allauth.mfa.recovery_codes.internal.auth import RecoveryCodes
from allauth.mfa.totp.internal.auth import (
    TOTP,
    format_hotp_value,
    generate_totp_secret,
    hotp_value,
)
from django.core import mail
from django.core.cache import cache
from django.test import Client

from accounts.models import User

if TYPE_CHECKING:
    from django.test.client import _MonkeyPatchedWSGIResponse as HttpResponse

AUTH_API = "/api/auth/browser/v1"
PASSWORD = "correct-horse-battery-staple"


@pytest.fixture(autouse=True)
def _clear_rate_limit_cache() -> Iterator[None]:
    """allauth stores its rate-limit counters in the cache, which must not leak between tests."""
    cache.clear()
    yield
    cache.clear()


class AuthApi:
    """Minimal client for the allauth headless API that enforces CSRF like a browser would."""

    def __init__(self) -> None:
        self.client = Client(enforce_csrf_checks=True)

    def _csrf_token(self) -> str:
        if "csrftoken" not in self.client.cookies:
            self.client.get(f"{AUTH_API}/config")
        return self.client.cookies["csrftoken"].value

    def call(self, method: str, url: str, data: dict[str, Any] | None = None) -> HttpResponse:
        return self.client.generic(
            method,
            url,
            data=b"" if data is None else json.dumps(data),
            content_type="application/json",
            headers={"X-CSRFToken": self._csrf_token()},
        )

    def request(self, method: str, path: str, data: dict[str, Any] | None = None) -> HttpResponse:
        return self.call(method, f"{AUTH_API}{path}", data)

    def login(self, email: str, password: str = PASSWORD) -> HttpResponse:
        return self.request("POST", "/auth/login", {"email": email, "password": password})

    def authenticate_mfa(self, code: str) -> HttpResponse:
        return self.request("POST", "/auth/2fa/authenticate", {"code": code})

    def reauthenticate(self, password: str = PASSWORD) -> HttpResponse:
        return self.request("POST", "/auth/reauthenticate", {"password": password})

    def login_with_totp(self, email: str, secret: str) -> HttpResponse:
        """Both steps of a sign-in for an account with an authenticator app."""
        self.login(email)
        return self.authenticate_mfa(totp_code(secret))

    @property
    def is_authenticated(self) -> bool:
        return self.client.get(f"{AUTH_API}/auth/session").status_code == HTTPStatus.OK


def totp_code(secret: str) -> str:
    """The code an authenticator app would show right now."""
    return format_hotp_value(hotp_value(secret, int(time.time()) // mfa_settings.TOTP_PERIOD))


@dataclass(frozen=True)
class SecondFactor:
    secret: str
    recovery_codes: list[str]


def enable_totp(user: User) -> SecondFactor:
    """Gives ``user`` an active authenticator app and recovery codes, like a finished setup."""
    secret = generate_totp_secret()
    TOTP.activate(user, secret)
    return SecondFactor(secret, RecoveryCodes.activate(user).get_unused_codes())


@pytest.fixture
def api() -> AuthApi:
    return AuthApi()


@pytest.fixture
def verified_user(db: None) -> User:
    user = User.objects.create_user("athlete@example.com", PASSWORD)
    EmailAddress.objects.create(user=user, email=user.email, primary=True, verified=True)
    return user


@pytest.fixture
def second_factor(verified_user: User) -> SecondFactor:
    """An authenticator app for ``verified_user``."""
    return enable_totp(verified_user)


@pytest.fixture
def verified_staff(db: None) -> User:
    admin = User.objects.create_superuser("admin@example.com", PASSWORD)
    EmailAddress.objects.create(user=admin, email=admin.email, primary=True, verified=True)
    return admin


def key_from_last_mail(url_part: str) -> str:
    """Extract the key from the frontend link in the most recently sent email.

    The key is percent-encoded in the URL; a router decodes the path parameter for the SPA.
    """
    body = str(mail.outbox[-1].body)
    match = re.search(rf"{re.escape(url_part)}/(\S+)", body)
    assert match, body
    return unquote(match.group(1))
