from http import HTTPStatus
from io import StringIO
from typing import Any

import pytest
from allauth.account.models import EmailAddress
from django.core.management import call_command
from django.core.management.base import CommandError

from accounts.models import User
from config import settings as production_settings

from .conftest import AuthApi

pytestmark = pytest.mark.django_db

EMAIL = "admin@example.com"
PASSWORD = "an-entirely-unguessable-passphrase"


@pytest.fixture(autouse=True)
def _no_ambient_setup_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SETUP_ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("SETUP_ADMIN_EMAIL", raising=False)


def run(**options) -> tuple[str, str]:
    out, err = StringIO(), StringIO()
    call_command("setup_admin", stdout=out, stderr=err, **options)
    return out.getvalue(), err.getvalue()


def test_creates_a_verified_admin_who_can_log_in(
    monkeypatch: pytest.MonkeyPatch, settings: Any
) -> None:
    settings.PASSWORD_HASHERS = production_settings.PASSWORD_HASHERS
    monkeypatch.setenv("SETUP_ADMIN_PASSWORD", PASSWORD)

    out, _ = run(email="Admin@Example.com", display_name="Ada")

    admin = User.objects.get()
    assert admin.email == EMAIL
    assert admin.is_staff
    assert admin.display_name == "Ada"
    assert admin.password.startswith("argon2$argon2id$")
    assert EmailAddress.objects.get(user=admin).verified
    assert EMAIL in out
    api = AuthApi()
    assert api.login(EMAIL, PASSWORD).status_code == HTTPStatus.OK


def test_email_can_come_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SETUP_ADMIN_PASSWORD", PASSWORD)
    monkeypatch.setenv("SETUP_ADMIN_EMAIL", EMAIL)

    run()

    assert User.objects.get().email == EMAIL


def test_password_is_prompted_for_and_never_printed(monkeypatch: pytest.MonkeyPatch) -> None:
    answers = iter([PASSWORD, PASSWORD])
    monkeypatch.setattr("accounts.management.commands.setup_admin.getpass", lambda _: next(answers))

    out, err = run(email=EMAIL)

    assert User.objects.get().check_password(PASSWORD)
    assert PASSWORD not in out + err


def test_mismatching_prompts_create_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    answers = iter([PASSWORD, PASSWORD + "x"])
    monkeypatch.setattr("accounts.management.commands.setup_admin.getpass", lambda _: next(answers))

    with pytest.raises(CommandError, match="do not match"):
        run(email=EMAIL)

    assert not User.objects.exists()


def test_refuses_to_run_twice(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SETUP_ADMIN_PASSWORD", PASSWORD)
    run(email=EMAIL)

    with pytest.raises(CommandError, match="administrator already exists"):
        run(email="second@example.com")

    assert User.objects.count() == 1


def test_refuses_when_any_admin_exists_even_if_inactive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SETUP_ADMIN_PASSWORD", PASSWORD)
    User.objects.create_superuser("old@example.com", PASSWORD, is_active=False)

    with pytest.raises(CommandError, match="administrator already exists"):
        run(email=EMAIL)


def test_refuses_an_email_that_belongs_to_a_regular_user(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SETUP_ADMIN_PASSWORD", PASSWORD)
    User.objects.create_user(EMAIL)

    with pytest.raises(CommandError, match="already exists"):
        run(email=EMAIL)

    assert not User.objects.filter(is_staff=True).exists()


def test_rejects_weak_passwords(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SETUP_ADMIN_PASSWORD", "password")

    with pytest.raises(CommandError):
        run(email=EMAIL)

    assert not User.objects.exists()


def test_requires_a_valid_email(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SETUP_ADMIN_PASSWORD", PASSWORD)

    with pytest.raises(CommandError, match="Provide --email"):
        run()
    with pytest.raises(CommandError, match="not a valid email"):
        run(email="not-an-email")

    assert not User.objects.exists()
