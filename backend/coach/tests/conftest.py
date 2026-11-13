from collections.abc import Iterator
from typing import Any

import pytest
from allauth.account.models import EmailAddress
from django.core.cache import cache

from accounts.models import User
from accounts.tests.conftest import PASSWORD, AuthApi

from .fake_providers import FakeProvider, running


@pytest.fixture(autouse=True)
def _no_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    """The fake server is on localhost; an environment proxy must not get in the way."""
    for name in ("http_proxy", "HTTP_PROXY", "https_proxy", "HTTPS_PROXY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("no_proxy", "127.0.0.1")


@pytest.fixture
def fake(settings: Any) -> Iterator[FakeProvider]:
    """A fake AI provider that the application talks to instead of the real Anthropic."""
    with running() as server:
        settings.ANTHROPIC_API_BASE_URL = server.url
        yield server


@pytest.fixture(autouse=True)
def _clear_cache() -> Iterator[None]:
    """Throttle counters live in the cache and must not leak between tests."""
    cache.clear()
    yield
    cache.clear()


def make_user(email: str) -> User:
    user = User.objects.create_user(email, PASSWORD)
    EmailAddress.objects.create(user=user, email=email, primary=True, verified=True)
    return user


def signed_in(user: User) -> AuthApi:
    api = AuthApi()
    assert api.login(user.email).status_code == 200
    return api
