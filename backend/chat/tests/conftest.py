from collections.abc import Callable, Iterator
from typing import Any

import pytest
from django.core.cache import cache

from accounts.models import User
from coach import services as coach_services
from integrations import services as integrations_services
from planning.tests.fake_calendar import Calendar, FakeClient
from planning.tests.scripted import Scripted
from reviews.tests.conftest import make_user


@pytest.fixture(autouse=True)
def _clear_cache() -> Iterator[None]:
    """The rate limits live in the cache: every test starts with a fresh count."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def alice() -> User:
    return make_user("alice@example.com")


@pytest.fixture
def bob() -> User:
    return make_user("bob@example.com")


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


@pytest.fixture
def calendar(monkeypatch: pytest.MonkeyPatch) -> Calendar:
    """An in-memory Intervals.icu calendar used in place of the real one."""
    calendar = Calendar()
    monkeypatch.setattr(
        integrations_services, "IntervalsClient", lambda key: FakeClient(calendar, key)
    )
    return calendar
