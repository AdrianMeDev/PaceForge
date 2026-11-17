from collections.abc import Iterator

import pytest
from django.core.cache import cache

from accounts.models import User
from reviews.tests.conftest import make_user


@pytest.fixture(autouse=True)
def _clear_cache() -> Iterator[None]:
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def alice() -> User:
    return make_user("alice@example.com")


@pytest.fixture
def bob() -> User:
    return make_user("bob@example.com")
