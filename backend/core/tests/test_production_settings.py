import runpy
from typing import Any

import environ
import pytest
from django.core.checks import run_checks
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.core.management.base import SystemCheckError
from django.test import RequestFactory

from config import settings as config_settings

STRONG_KEY = "k7Qz-Vh2mXp9LdR4tYw8NcB6sUe3JfGa1oIyHb5KxZv0MqTnAr"


@pytest.fixture
def read_settings(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Read ``config/settings.py`` afresh from a clean environment plus the given variables."""
    for name in (
        "APP_DOMAIN",
        "DJANGO_DEBUG",
        "DJANGO_ALLOWED_HOSTS",
        "DJANGO_CSRF_TRUSTED_ORIGINS",
        "DJANGO_TRUST_PROXY_HEADERS",
        "DJANGO_HSTS_SECONDS",
        "DATABASE_CONN_MAX_AGE",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(environ.Env, "read_env", classmethod(lambda cls, *a, **k: None))

    def read(**env: str) -> dict[str, Any]:
        for name, value in env.items():
            monkeypatch.setenv(name, value)
        return runpy.run_path(config_settings.__file__)

    return read


class TestAppDomain:
    def test_it_is_the_default_for_hosts_and_csrf_origins(self, read_settings: Any) -> None:
        read = read_settings(APP_DOMAIN="Pace.Example.com")

        assert read["APP_DOMAIN"] == "pace.example.com"
        assert read["ALLOWED_HOSTS"] == ["pace.example.com"]
        assert read["CSRF_TRUSTED_ORIGINS"] == ["https://pace.example.com"]

    def test_explicit_values_win(self, read_settings: Any) -> None:
        read = read_settings(
            APP_DOMAIN="pace.example.com",
            DJANGO_ALLOWED_HOSTS="a.example.com,b.example.com",
            DJANGO_CSRF_TRUSTED_ORIGINS="https://a.example.com",
        )

        assert read["ALLOWED_HOSTS"] == ["a.example.com", "b.example.com"]
        assert read["CSRF_TRUSTED_ORIGINS"] == ["https://a.example.com"]

    def test_debug_mode_adds_no_csrf_origin(self, read_settings: Any) -> None:
        read = read_settings(APP_DOMAIN="pace.example.com", DJANGO_DEBUG="true")

        assert read["ALLOWED_HOSTS"] == ["pace.example.com"]
        assert read["CSRF_TRUSTED_ORIGINS"] == []

    def test_without_a_domain_nothing_is_allowed(self, read_settings: Any) -> None:
        read = read_settings()

        assert read["ALLOWED_HOSTS"] == []
        assert read["CSRF_TRUSTED_ORIGINS"] == []

    @pytest.mark.parametrize(
        "bad",
        [
            "https://pace.example.com",
            "pace.example.com/app",
            "pace.example.com:8000",
            "a b",
            "-x.com",
        ],
    )
    def test_anything_but_a_host_name_is_refused(self, read_settings: Any, bad: str) -> None:
        with pytest.raises(ImproperlyConfigured, match="APP_DOMAIN"):
            read_settings(APP_DOMAIN=bad)


class TestProductionDefaults:
    def test_production_defaults(self, read_settings: Any) -> None:
        read = read_settings()

        assert read["SECURE_PROXY_SSL_HEADER"] == ("HTTP_X_FORWARDED_PROTO", "https")
        assert read["ACCOUNT_DEFAULT_HTTP_PROTOCOL"] == "https"
        assert read["SECURE_HSTS_SECONDS"] == 31536000
        assert read["CONN_MAX_AGE"] == 60
        assert read["DATABASES"]["default"]["CONN_MAX_AGE"] == 60
        assert read["DATABASES"]["default"]["CONN_HEALTH_CHECKS"] is True
        assert read["SECURE_CONTENT_TYPE_NOSNIFF"] is True
        assert read["X_FRAME_OPTIONS"] == "DENY"

    def test_debug_defaults(self, read_settings: Any) -> None:
        read = read_settings(DJANGO_DEBUG="true")

        assert "SECURE_PROXY_SSL_HEADER" not in read
        assert read["ACCOUNT_DEFAULT_HTTP_PROTOCOL"] == "http"
        assert read["SECURE_HSTS_SECONDS"] == 0

    def test_overrides(self, read_settings: Any) -> None:
        read = read_settings(
            DJANGO_TRUST_PROXY_HEADERS="false",
            DJANGO_HSTS_SECONDS="600",
            DATABASE_CONN_MAX_AGE="0",
        )

        assert "SECURE_PROXY_SSL_HEADER" not in read
        assert read["SECURE_HSTS_SECONDS"] == 600
        assert read["DATABASES"]["default"]["CONN_MAX_AGE"] == 0

    def test_negative_numbers_are_refused(self, read_settings: Any) -> None:
        with pytest.raises(ImproperlyConfigured, match="DJANGO_HSTS_SECONDS"):
            read_settings(DJANGO_HSTS_SECONDS="-1")

    def test_logs_go_to_stderr(self, read_settings: Any) -> None:
        logging: dict[str, Any] = read_settings()["LOGGING"]

        assert logging["handlers"]["stderr"]["stream"] == "ext://sys.stderr"
        assert logging["root"] == {"handlers": ["stderr"], "level": "WARNING"}


class TestForwardedProto:
    def test_the_header_makes_urls_https(self, settings: Any) -> None:
        settings.SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
        settings.ALLOWED_HOSTS = ["pace.example.com"]
        request = RequestFactory().get(
            "/", HTTP_HOST="pace.example.com", HTTP_X_FORWARDED_PROTO="https"
        )

        assert request.is_secure()
        url = request.build_absolute_uri(settings.HEADLESS_FRONTEND_URLS["account_signup"])
        assert url == "https://pace.example.com/account/signup"

    def test_without_the_header_urls_stay_http(self, settings: Any) -> None:
        settings.SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
        settings.ALLOWED_HOSTS = ["pace.example.com"]
        request = RequestFactory().get("/", HTTP_HOST="pace.example.com")

        assert request.build_absolute_uri("/x").startswith("http://")

    def test_invitation_links_use_https(self, settings: Any) -> None:
        settings.SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
        settings.ALLOWED_HOSTS = ["pace.example.com"]
        request = RequestFactory().get(
            "/", HTTP_HOST="pace.example.com", HTTP_X_FORWARDED_PROTO="https"
        )

        link = request.build_absolute_uri("/account/signup?invitation=t&email=a%40b.c")
        assert link.startswith("https://pace.example.com/account/signup?")


@pytest.fixture
def production(settings: Any) -> Any:
    settings.DEBUG = False
    settings.ALLOWED_HOSTS = ["pace.example.com"]
    settings.SECRET_KEY = STRONG_KEY
    settings.CSRF_TRUSTED_ORIGINS = ["https://pace.example.com"]
    return settings


def deploy_ids() -> set[str]:
    return {message.id for message in run_checks(include_deployment_checks=True) if message.id}


class TestDeployChecks:
    def test_a_valid_production_setup_passes(self, production: Any) -> None:
        assert not deploy_ids() & {"core.E003", "core.E004", "core.E005"}

    def test_empty_allowed_hosts(self, production: Any) -> None:
        production.ALLOWED_HOSTS = []

        assert "core.E003" in deploy_ids()

    @pytest.mark.parametrize("key", ["short", "change-me-" + "x" * 60, "x" * 20])
    def test_weak_or_placeholder_secret_keys(self, production: Any, key: str) -> None:
        production.SECRET_KEY = key

        assert "core.E004" in deploy_ids()

    def test_the_secret_is_not_in_the_message(self, production: Any) -> None:
        production.SECRET_KEY = "change-me-dev-only"

        messages = [m for m in run_checks(include_deployment_checks=True) if m.id == "core.E004"]
        assert "change-me-dev-only" not in str(messages)

    def test_http_csrf_origins(self, production: Any) -> None:
        production.CSRF_TRUSTED_ORIGINS = ["https://pace.example.com", "http://pace.example.com"]

        assert "core.E005" in deploy_ids()

    def test_debug_mode_skips_the_checks(self, production: Any) -> None:
        production.DEBUG = True
        production.ALLOWED_HOSTS = []
        production.SECRET_KEY = "x"

        assert not deploy_ids() & {"core.E003", "core.E004", "core.E005"}

    def test_the_command_fails_on_a_bad_setup(self, production: Any) -> None:
        production.ALLOWED_HOSTS = []

        with pytest.raises(SystemCheckError, match="core.E003"):
            call_command("check", "--deploy", "--fail-level", "ERROR")

    def test_plain_check_ignores_the_deploy_checks(self, production: Any) -> None:
        production.ALLOWED_HOSTS = []
        production.SECRET_KEY = "x"

        call_command("check")
