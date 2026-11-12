"""Authenticated encryption for secrets that are stored in the database.

Secrets (TOTP seeds, provider tokens, API keys) are encrypted with Fernet (AES-128-CBC with an
HMAC-SHA256 tag and a random IV), so a stolen database backup reveals nothing without the instance
key and a modified value is rejected instead of decrypted to something else. The key lives in
``ENCRYPTION_KEY`` and never in the database or the repository.

``ENCRYPTION_KEY`` may hold several keys separated by commas: the first one encrypts, all of them
decrypt. Putting a new key in front keeps everything encrypted with the old one readable.
"""

from functools import cache

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

# Marks the format of a stored value. A value without it is not ciphertext of ours, so legacy
# plaintext is never mistaken for something that was verified.
PREFIX = "enc:v1:"


class DecryptionError(Exception):
    """A stored value cannot be decrypted: wrong key, damaged, or not encrypted at all.

    The message never contains the value or key material, so it is safe to log.
    """


@cache
def _cipher(keys: tuple[str, ...]) -> MultiFernet:
    return MultiFernet([Fernet(key) for key in keys])


def _current_cipher() -> MultiFernet:
    keys = tuple(settings.ENCRYPTION_KEYS)
    if not keys:
        raise ImproperlyConfigured("ENCRYPTION_KEY is not configured.")
    return _cipher(keys)


def encrypt(text: str) -> str:
    """Return ``text`` as a self-describing token, a different one for every call."""
    token = _current_cipher().encrypt(text.encode())
    return PREFIX + token.decode("ascii")


def decrypt(stored: str) -> str:
    if not stored.startswith(PREFIX):
        raise DecryptionError("The value is not encrypted with the instance key.")
    try:
        return _current_cipher().decrypt(stored[len(PREFIX) :].encode()).decode()
    except InvalidToken, UnicodeDecodeError:
        raise DecryptionError(
            "The value could not be decrypted: wrong ENCRYPTION_KEY or damaged data."
        ) from None
