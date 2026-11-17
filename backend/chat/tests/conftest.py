from collections.abc import Callable
from typing import Any

import pytest

from accounts.models import User
from coach import services as coach_services
from planning.tests.scripted import Scripted
from reviews.tests.conftest import make_user


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
