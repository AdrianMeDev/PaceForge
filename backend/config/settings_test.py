"""Settings used by the test suite only."""

import os

os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-secret-key-not-for-production")
# Matches the defaults of the `db` service in compose.dev.yaml.
os.environ.setdefault(
    "DATABASE_URL", "postgres://paceforge:paceforge-dev@localhost:5432/paceforge"
)

from .settings import *  # noqa: E402, F403
