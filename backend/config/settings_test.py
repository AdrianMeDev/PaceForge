"""Settings used by the test suite only."""

import os

os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-secret-key-not-for-production")

from .settings import *  # noqa: E402, F403
