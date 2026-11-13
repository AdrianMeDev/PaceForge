"""The addresses an operator allows for AI providers.

Pure functions without Django imports besides the settings error: ``config/settings.py`` uses them
while it is being read.
"""

from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured


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
        found_one = _normal_form(text)
        if found_one is None:
            raise ImproperlyConfigured(
                f"{setting}, entry {position}: use http:// or https://, a host, an optional port "
                "and path, and no user name, password, query or fragment."
            )
        if found_one not in found:
            found.append(found_one)
    return tuple(found)


def _normal_form(text: str) -> str | None:
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
    return f"{parts.scheme}://{netloc}{parts.path.rstrip('/')}"
