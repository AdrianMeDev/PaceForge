from http import HTTPStatus

import pytest

from accounts.models import User

from .conftest import AuthApi

pytestmark = pytest.mark.django_db

ME = "/api/me/"


def test_anonymous_users_are_refused(api: AuthApi) -> None:
    assert api.call("GET", ME).status_code == HTTPStatus.FORBIDDEN


def test_returns_only_the_own_account(
    api: AuthApi, verified_user: User, verified_staff: User
) -> None:
    api.login(verified_user.email)

    response = api.call("GET", ME)

    assert response.status_code == HTTPStatus.OK
    assert response.json() == {
        "id": str(verified_user.pk),
        "email": "athlete@example.com",
        "display_name": "",
        "is_staff": False,
    }
    assert verified_staff.email not in response.content.decode()


def test_never_exposes_credentials(api: AuthApi, verified_user: User) -> None:
    api.login(verified_user.email)

    body = api.call("GET", ME).json()

    assert "password" not in body
    assert "last_login" not in body


def test_flags_administrators(api: AuthApi, verified_staff: User) -> None:
    api.login(verified_staff.email)

    assert api.call("GET", ME).json()["is_staff"] is True
