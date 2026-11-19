from typing import Any
from urllib.parse import urlsplit

from cryptography.fernet import Fernet
from django.conf import settings
from django.core.checks import CheckMessage, Error

GENERATE_HINT = (
    'Generate one with: uv run python -c "from cryptography.fernet import Fernet; '
    'print(Fernet.generate_key().decode())"'
)


def check_encryption_keys(app_configs: Any, **kwargs: Any) -> list[CheckMessage]:
    """Fail at startup, by variable name only: a key must never end up in an error message."""
    keys: list[str] = settings.ENCRYPTION_KEYS
    if not keys:
        return [Error(f"ENCRYPTION_KEY is empty. {GENERATE_HINT}", id="core.E001")]
    errors: list[CheckMessage] = []
    for position, key in enumerate(keys, start=1):
        try:
            Fernet(key)
        except ValueError:
            errors.append(
                Error(
                    f"Key {position} of ENCRYPTION_KEY is not a valid key (32 bytes, "
                    f"url-safe base64). {GENERATE_HINT}",
                    id="core.E002",
                )
            )
    return errors


WEAK_SECRET_MARKERS = ("change-me", "changeme", "insecure", "secret-key", "placeholder", "example")


def check_deployment(app_configs: Any, **kwargs: Any) -> list[CheckMessage]:
    """Production only (``manage.py check --deploy``); never prints the secret itself."""
    if settings.DEBUG:
        return []
    errors: list[CheckMessage] = []
    if not settings.ALLOWED_HOSTS:
        errors.append(
            Error(
                "ALLOWED_HOSTS is empty. Set APP_DOMAIN or DJANGO_ALLOWED_HOSTS.",
                id="core.E003",
            )
        )
    secret: str = settings.SECRET_KEY
    if len(secret) < 50 or any(marker in secret.lower() for marker in WEAK_SECRET_MARKERS):
        errors.append(
            Error(
                "DJANGO_SECRET_KEY is weak or a placeholder. Use at least 50 random characters.",
                id="core.E004",
            )
        )
    for origin in settings.CSRF_TRUSTED_ORIGINS:
        if urlsplit(origin).scheme != "https":
            errors.append(
                Error(
                    "DJANGO_CSRF_TRUSTED_ORIGINS must only contain https:// origins "
                    "when DJANGO_DEBUG is off.",
                    id="core.E005",
                )
            )
            break
    return errors
