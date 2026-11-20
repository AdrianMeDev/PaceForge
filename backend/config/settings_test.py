"""Settings used by the test suite only."""

import os
from pathlib import Path

import environ

os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-secret-key-not-for-production")
# A throw-away instance key; it protects nothing.
os.environ.setdefault("ENCRYPTION_KEY", "srPGFiK_-1uuYQrhJix9QxALddGxwSw-I5bllic4QsY=")
# Read `.env` if there is one (shell variables win), so the defaults below only fill what it
# leaves out. No password is set here: POSTGRES_PASSWORD comes from the environment, `.env` or
# ~/.pgpass.
_env_file = Path(__file__).resolve().parent.parent.parent / ".env"
if _env_file.is_file():
    environ.Env.read_env(_env_file, overwrite=False)
if not os.environ.get("DATABASE_URL", "").strip():
    # Match the defaults of the `db` service in compose.dev.yaml.
    os.environ.setdefault("POSTGRES_HOST", "localhost")
    os.environ.setdefault("POSTGRES_PORT", "5432")
    os.environ.setdefault("POSTGRES_USER", "paceforge")
    os.environ.setdefault("POSTGRES_DB", "paceforge")

from .settings import *  # noqa: E402, F403

# The AI settings are the defaults here, whatever the operator wrote into `.env` (a machine that
# allows DeepSeek must not turn tests red): tests that need an address list their own, and the
# real defaults are tested against a fresh read of `settings.py` (coach/tests/test_endpoints.py).
AI_ALLOWED_BASE_URLS = ()
ANTHROPIC_API_BASE_URL = "https://api.anthropic.com"

# Concrete OwnedModel for the core tests; its tables are created without migrations.
INSTALLED_APPS = [*INSTALLED_APPS, "core.tests.sample"]  # noqa: F405

# A code computed at the end of a 30 s period must still be accepted when it is checked a moment
# later; production keeps allauth's default of 0.
MFA_TOTP_TOLERANCE = 1

# Argon2 is slow on purpose (about 30 ms a hash) and almost every test creates a user with a
# password. The tests that check the production hashers set them with the `settings` fixture
# (`accounts/tests/test_models.py`, `accounts/tests/test_setup_admin.py`).
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Keep retryable 429/5xx tests fast; retry behaviour itself is tested with explicit delays.
INTERVALS_RETRY_DELAYS = (0.0, 0.0, 0.0)
