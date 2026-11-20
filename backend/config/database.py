"""Database settings from the environment, without echoing credentials in errors."""

from typing import Any

import environ
from django.core.exceptions import ImproperlyConfigured


def database_from_env(env: environ.Env) -> dict[str, Any]:
    """Build ``DATABASES["default"]``.

    A non-empty ``DATABASE_URL`` wins. Otherwise the discrete ``POSTGRES_*`` variables are used,
    so a password with URL-reserved characters (``@:/?#%&+=``) is never put through a URL.
    Values are read raw from the environment: django-environ would treat a leading ``$`` as a
    reference to another variable.
    """
    raw = env.ENVIRON
    url = raw.get("DATABASE_URL", "")
    if url.strip():
        return dict(env.db_url_config(url))

    name = raw.get("POSTGRES_DB", "")
    user = raw.get("POSTGRES_USER", "")
    missing = [
        variable
        for variable, value in (("POSTGRES_DB", name), ("POSTGRES_USER", user))
        if not value.strip()
    ]
    if missing:
        raise ImproperlyConfigured(
            "Database is not configured: set DATABASE_URL or "
            + " and ".join(missing)
            + " (plus POSTGRES_PASSWORD)"
        )

    port_text = raw.get("POSTGRES_PORT", "").strip() or "5432"
    try:
        port = int(port_text)
    except ValueError:
        port = 0
    if not 1 <= port <= 65535:
        raise ImproperlyConfigured("POSTGRES_PORT must be a whole number from 1 to 65535")

    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": name,
        "USER": user,
        "PASSWORD": raw.get("POSTGRES_PASSWORD", ""),
        "HOST": raw.get("POSTGRES_HOST", "").strip() or "localhost",
        "PORT": str(port),
    }
