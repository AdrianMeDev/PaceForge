import runpy
from typing import Any

import environ
import pytest
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from coach.endpoints import parse_base_urls
from config import settings as config_settings


def parse(*values: str) -> tuple[str, ...]:
    return parse_base_urls("SETTING", list(values))


class TestAcceptedAddresses:
    @pytest.mark.parametrize(
        ("given", "expected"),
        [
            ("https://api.openai.com/v1", "https://api.openai.com/v1"),
            ("https://api.openai.com/v1/", "https://api.openai.com/v1"),
            ("https://api.openai.com/v1///", "https://api.openai.com/v1"),
            ("http://localhost:11434/v1", "http://localhost:11434/v1"),
            ("http://localhost:11434", "http://localhost:11434"),
            ("http://localhost:11434/", "http://localhost:11434"),
            ("HTTPS://API.OpenAI.com/v1", "https://api.openai.com/v1"),
            ("http://127.0.0.1:8080/v1", "http://127.0.0.1:8080/v1"),
            ("http://[::1]:8080/v1", "http://[::1]:8080/v1"),
            ("  https://example.org/a/b  ", "https://example.org/a/b"),
            ("http://llm.internal", "http://llm.internal"),
        ],
    )
    def test_the_normal_form(self, given: str, expected: str) -> None:
        assert parse(given) == (expected,)

    def test_nothing_gives_nothing(self) -> None:
        assert parse_base_urls("SETTING", []) == ()

    def test_empty_entries_are_skipped(self) -> None:
        assert parse("", "  ", "https://a.example") == ("https://a.example",)

    def test_duplicates_are_dropped_and_the_order_is_kept(self) -> None:
        result = parse("https://b.example", "https://a.example/", "https://b.example/")

        assert result == ("https://b.example", "https://a.example")


class TestRefusedAddresses:
    @pytest.mark.parametrize(
        "bad",
        [
            "ftp://example.org",
            "file:///etc/passwd",
            "javascript:alert(1)",
            "example.org",
            "//example.org",
            "https://",
            "http:///path",
            "https://user@example.org",
            "https://user:secret@example.org",
            "https://:secret@example.org",
            "https://example.org/v1?key=abc",
            "https://example.org/v1?",
            "https://example.org/v1#frag",
            "https://example.org/v1#",
            "http://example.org:notaport",
            "http://example.org:99999",
            "http://example.org:-1",
        ],
    )
    def test_is_refused_at_startup(self, bad: str) -> None:
        with pytest.raises(ImproperlyConfigured):
            parse(bad)

    def test_the_message_names_the_setting_and_the_position_but_not_the_value(self) -> None:
        with pytest.raises(ImproperlyConfigured) as raised:
            parse_base_urls(
                "AI_ALLOWED_BASE_URLS", ["https://ok.example", "https://u:pw@x.example"]
            )

        message = str(raised.value)
        assert "AI_ALLOWED_BASE_URLS" in message
        assert "entry 2" in message
        assert "pw" not in message
        assert "x.example" not in message

    def test_one_bad_entry_spoils_the_list(self) -> None:
        with pytest.raises(ImproperlyConfigured):
            parse("https://ok.example", "ftp://bad.example")


class TestTheSettings:
    """The defaults of ``config/settings.py``, read afresh: not what the test run was given, and
    not what the operator wrote into ``.env`` (django-environ never overwrites a variable that is
    set, so deleting it and skipping the file leaves the default)."""

    @pytest.fixture
    def defaults(self, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
        for name in ("AI_ALLOWED_BASE_URLS", "ANTHROPIC_API_BASE_URL"):
            monkeypatch.delenv(name, raising=False)
        monkeypatch.setattr(environ.Env, "read_env", classmethod(lambda cls, *a, **k: None))
        return runpy.run_path(config_settings.__file__)

    def test_no_openai_compatible_address_is_allowed_by_default(
        self, defaults: dict[str, Any]
    ) -> None:
        assert defaults["AI_ALLOWED_BASE_URLS"] == ()

    def test_anthropic_is_at_home_by_default(self, defaults: dict[str, Any]) -> None:
        assert defaults["ANTHROPIC_API_BASE_URL"] == "https://api.anthropic.com"

    def test_a_variable_is_read(
        self, defaults: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(
            "AI_ALLOWED_BASE_URLS", "https://api.deepseek.com, https://openrouter.ai/api/v1/"
        )

        read = runpy.run_path(config_settings.__file__)

        assert read["AI_ALLOWED_BASE_URLS"] == (
            "https://api.deepseek.com",
            "https://openrouter.ai/api/v1",
        )

    def test_the_test_run_itself_is_independent_of_the_env_file(self) -> None:
        assert settings.AI_ALLOWED_BASE_URLS == ()
        assert settings.ANTHROPIC_API_BASE_URL == "https://api.anthropic.com"
