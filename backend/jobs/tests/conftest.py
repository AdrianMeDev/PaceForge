"""Shared fixtures of the job tests."""

from datetime import UTC, datetime

import pytest

from accounts.models import User
from goals import services as goal_services

PASSWORD = "correct horse battery staple"
NOW = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)


def make_user(email: str) -> User:
    """A user with a verified address, ready to own data."""
    return User.objects.create_user(email, PASSWORD)


@pytest.fixture(autouse=True)
def _today(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fix the clock, so a job's ``newest`` day is the same in every test."""
    monkeypatch.setattr(goal_services, "_utc_now", lambda: NOW)


@pytest.fixture(autouse=True)
def _no_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    """The fake Intervals.icu is on localhost; an environment proxy must not get in the way."""
    for name in ("http_proxy", "HTTP_PROXY", "https_proxy", "HTTPS_PROXY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("no_proxy", "127.0.0.1")
