from collections.abc import Iterator
from typing import Any

import pytest

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
