import pytest
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from coach.endpoints import parse_base_urls


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
    def test_no_openai_compatible_address_is_allowed_by_default(self) -> None:
        assert settings.AI_ALLOWED_BASE_URLS == ()

    def test_anthropic_is_at_home_by_default(self) -> None:
        assert settings.ANTHROPIC_API_BASE_URL == "https://api.anthropic.com"
