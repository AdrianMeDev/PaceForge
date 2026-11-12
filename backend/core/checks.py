from typing import Any

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
