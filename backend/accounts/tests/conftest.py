import json
import re
from collections.abc import Iterator
from http import HTTPStatus
from typing import Any
from urllib.parse import unquote

import pytest
from allauth.account.models import EmailAddress
from django.core import mail
from django.core.cache import cache
from django.http import HttpResponse
from django.test import Client

from accounts.models import User

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

    @property
    def is_authenticated(self) -> bool:
        return self.client.get(f"{AUTH_API}/auth/session").status_code == HTTPStatus.OK


@pytest.fixture
def api() -> AuthApi:
    return AuthApi()


@pytest.fixture
def verified_user(db: None) -> User:
    user = User.objects.create_user("athlete@example.com", PASSWORD)
    EmailAddress.objects.create(user=user, email=user.email, primary=True, verified=True)
    return user


@pytest.fixture
def verified_staff(db: None) -> User:
    admin = User.objects.create_superuser("admin@example.com", PASSWORD)
    EmailAddress.objects.create(user=admin, email=admin.email, primary=True, verified=True)
    return admin


def key_from_last_mail(url_part: str) -> str:
    """Extract the key from the frontend link in the most recently sent email.

    The key is percent-encoded in the URL; a router decodes the path parameter for the SPA.
    """
    match = re.search(rf"{re.escape(url_part)}/(\S+)", mail.outbox[-1].body)
    assert match, mail.outbox[-1].body
    return unquote(match.group(1))
