from collections.abc import Iterator

import pytest
from allauth.account.models import EmailAddress
from django.core.cache import cache

from accounts.models import User
from accounts.tests.conftest import PASSWORD, AuthApi


@pytest.fixture(autouse=True)
def _clear_cache() -> Iterator[None]:
    """Throttle counters live in the cache and must not leak between tests."""
    cache.clear()
    yield
    cache.clear()


def make_user(email: str, *, staff: bool = False) -> User:
    user = User.objects.create_user(email, PASSWORD, is_staff=staff)
    EmailAddress.objects.create(user=user, email=email, primary=True, verified=True)
    return user


def signed_in(user: User) -> AuthApi:
    api = AuthApi()
    assert api.login(user.email).status_code == 200
    return api
