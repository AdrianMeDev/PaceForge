from typing import Any

import pytest
from django.contrib.auth import authenticate
from django.db import IntegrityError, transaction

from accounts.models import User
from config import settings as production_settings

pytestmark = pytest.mark.django_db

PRODUCTION_HASHERS = production_settings.PASSWORD_HASHERS


def test_create_user_uses_email_and_defaults() -> None:
    user = User.objects.create_user("Athlete@Example.COM ", "s3cure-passphrase", display_name="Ann")

    assert user.email == "athlete@example.com"
    assert user.display_name == "Ann"
    assert user.is_active
    assert not user.is_staff
    assert user.pk.version == 7


def test_password_is_hashed_with_argon2id(settings: Any) -> None:
    settings.PASSWORD_HASHERS = PRODUCTION_HASHERS
    user = User.objects.create_user("a@example.com", "s3cure-passphrase")

    assert user.password.startswith("argon2$argon2id$")
    assert user.check_password("s3cure-passphrase")


def test_the_production_settings_put_argon2id_first() -> None:
    assert PRODUCTION_HASHERS[0] == "django.contrib.auth.hashers.Argon2PasswordHasher"


def test_the_test_settings_hash_quickly() -> None:
    from django.conf import settings as active

    assert active.PASSWORD_HASHERS == ["django.contrib.auth.hashers.MD5PasswordHasher"]


def test_create_user_without_password_has_unusable_password() -> None:
    user = User.objects.create_user("invited@example.com")

    assert not user.has_usable_password()


def test_create_user_requires_email() -> None:
    with pytest.raises(ValueError):
        User.objects.create_user("", "s3cure-passphrase")


def test_create_superuser_is_staff() -> None:
    admin = User.objects.create_superuser("admin@example.com", "s3cure-passphrase")

    assert admin.is_staff


def test_email_is_unique_case_insensitively() -> None:
    User.objects.create_user("a@example.com")

    # `objects.create` bypasses the manager's normalisation, so the DB constraint must catch it.
    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.create(email="A@Example.com")


def test_login_with_email_is_case_insensitive() -> None:
    user = User.objects.create_user("a@example.com", "s3cure-passphrase")

    assert authenticate(email="A@EXAMPLE.com", password="s3cure-passphrase") == user
    assert authenticate(email="a@example.com", password="wrong") is None


def test_inactive_user_cannot_authenticate() -> None:
    User.objects.create_user("a@example.com", "s3cure-passphrase", is_active=False)

    assert authenticate(email="a@example.com", password="s3cure-passphrase") is None
