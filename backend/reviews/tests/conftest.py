from collections.abc import Callable, Iterator
from typing import Any

import pytest
from allauth.account.models import EmailAddress
from django.core.cache import cache

from accounts.models import User
from accounts.tests.conftest import PASSWORD, AuthApi
from coach import services as coach_services
from planning.tests.scripted import Scripted


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


@pytest.fixture
def provide(monkeypatch: pytest.MonkeyPatch) -> Callable[..., Scripted]:
    """Install a provider that answers from a list, in place of the user's real one."""

    def install(*replies: Any) -> Scripted:
        scripted = Scripted(*replies)
        monkeypatch.setattr(
            coach_services, "provider_for", lambda configuration, model=None: scripted
        )
        return scripted

    return install
