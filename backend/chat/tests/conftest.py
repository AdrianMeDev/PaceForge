import pytest

from accounts.models import User
from reviews.tests.conftest import make_user


@pytest.fixture
def alice() -> User:
    return make_user("alice@example.com")


@pytest.fixture
def bob() -> User:
    return make_user("bob@example.com")
