"""The addresses an operator allows for AI providers.

Pure functions without Django imports besides the settings error: ``config/settings.py`` uses them
while it is being read.
"""

import re
from collections.abc import Sequence
from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured

# Python and PostgreSQL both support these anchors. API prefixes such as /v1 are allowed.
_PORT = (
    r"(?:[1-9][0-9]{0,3}|[1-5][0-9]{4}|6[0-4][0-9]{3}|65[0-4][0-9]{2}|655[0-2][0-9]|6553[0-5]|0)"
)
# List Unicode whitespace explicitly as PostgreSQL's \s depends on its locale. NUL is
# rejected by normalize_base_url and cannot be stored in PostgreSQL text at all.
_FORBIDDEN = r"\s\x01-\x1f\x7f-\x9f" + "\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000"
BASE_URL_DB_PATTERN = (
    r"\Ahttps?://(?:[a-z0-9._~-]+|\[[0-9a-f:.]+\])"
    rf"(?::{_PORT})?"
    rf"(?:/[^{_FORBIDDEN}?#]*[^/{_FORBIDDEN}?#])?\Z"
)


def resolve_allowed_base_url(address: str, allowed: Sequence[str]) -> str | None:
    """Return the matching canonical entry, refusing even matching malformed settings.

    Configuration and calls require the exact canonical text of the parsed allowlist.
    """
    if normalize_base_url(address) != address:
        return None
    return next((entry for entry in allowed if entry == address), None)


def parse_base_urls(setting: str, values: list[str]) -> tuple[str, ...]:
    """The base URLs in ``values`` in a normal form (lower-case host, no trailing slash), without
    duplicates. Only ``http`` and ``https``, a host, no user name or password, no query and no
    fragment: anything else stops Django at startup. The messages name the setting and the
    position, never the value, which could hold a password."""
    found: list[str] = []
    for position, raw in enumerate(values, start=1):
        text = raw.strip()
        if not text:
            continue
        found_one = normalize_base_url(text)
        if found_one is None:
            raise ImproperlyConfigured(
                f"{setting}, entry {position}: use http:// or https://, a host, an optional port "
                "and path, and no user name, password, query or fragment."
            )
        if found_one not in found:
            found.append(found_one)
    return tuple(found)


def normalize_base_url(text: str) -> str | None:
    """Normalize an HTTP(S) base URL, refusing whitespace and control characters."""
    if any(
        character.isspace() or ord(character) < 32 or 127 <= ord(character) <= 159
        for character in text
    ):
        return None
    try:
        parts = urlsplit(text)
        port = parts.port  # raises ValueError for a port that is no number or out of range
    except ValueError:
        return None
    if (
        parts.scheme not in {"http", "https"}
        or not parts.hostname
        or parts.username is not None  # a password always comes with a (maybe empty) user name
        or "?" in text  # a query, even an empty one
        or "#" in text  # a fragment, even an empty one
    ):
        return None
    host = parts.hostname
    if ":" in host:  # an IPv6 address
        host = f"[{host}]"
    netloc = host if port is None else f"{host}:{port}"
    normalized = f"{parts.scheme}://{netloc}{parts.path.rstrip('/')}"
    return normalized if re.fullmatch(BASE_URL_DB_PATTERN, normalized) else None
