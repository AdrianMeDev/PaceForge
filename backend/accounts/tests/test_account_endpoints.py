import json
from http import HTTPStatus
from unittest.mock import patch

import pytest
from allauth.account.models import EmailAddress
from django.test import Client
from django.utils import timezone
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from accounts.models import User
from athletes.models import AthleteProfile

from .conftest import PASSWORD, AuthApi, SecondFactor

pytestmark = pytest.mark.django_db

EXPORT = "/api/me/export/"
DELETE = "/api/me/delete/"


def delete_body(user: User, **extra: str) -> dict[str, str]:
    return {"confirmation": user.email, "password": PASSWORD, **extra}


def other_user(email: str = "other@example.com") -> User:
    user = User.objects.create_user(email, PASSWORD)
    EmailAddress.objects.create(user=user, email=email, primary=True, verified=True)
    return user


def test_anonymous_users_are_refused(api: AuthApi, verified_user: User) -> None:
    assert api.call("GET", EXPORT).status_code == HTTPStatus.FORBIDDEN
    assert api.call("POST", DELETE, delete_body(verified_user)).status_code == HTTPStatus.FORBIDDEN
    assert User.objects.filter(pk=verified_user.pk).exists()


@pytest.mark.parametrize(
    ("method", "url"),
    [("GET", EXPORT), ("HEAD", EXPORT), ("OPTIONS", EXPORT), ("POST", DELETE), ("OPTIONS", DELETE)],
)
def test_anonymous_users_are_refused_when_defaults_allow_any(
    api: AuthApi, verified_user: User, monkeypatch: pytest.MonkeyPatch, method: str, url: str
) -> None:
    monkeypatch.setattr(APIView, "permission_classes", [AllowAny])
    AthleteProfile.objects.create(owner=verified_user)
    users_before = list(User.objects.values())
    profiles_before = list(AthleteProfile.objects.values())

    with (
        patch("accounts.views.build_user_export") as export,
        patch("accounts.views.delete_account") as delete,
    ):
        response = api.call(method, url, delete_body(verified_user))

    assert response.status_code == HTTPStatus.FORBIDDEN
    export.assert_not_called()
    delete.assert_not_called()
    assert list(User.objects.values()) == users_before
    assert list(AthleteProfile.objects.values()) == profiles_before


def test_delete_requires_a_csrf_token(api: AuthApi, verified_user: User) -> None:
    api.login(verified_user.email)
    csrf_less = Client(enforce_csrf_checks=True)
    csrf_less.cookies = api.client.cookies

    response = csrf_less.post(DELETE, delete_body(verified_user), content_type="application/json")

    assert response.status_code == HTTPStatus.FORBIDDEN
    assert User.objects.filter(pk=verified_user.pk).exists()


def test_export_is_a_json_download(api: AuthApi, verified_user: User) -> None:
    api.login(verified_user.email)

    response = api.call("GET", EXPORT)

    assert response.status_code == HTTPStatus.OK
    assert response["Content-Type"] == "application/json"
    assert response["Cache-Control"] == "no-store"
    assert response["Content-Disposition"] == (
        f'attachment; filename="paceforge-export-{timezone.localdate().isoformat()}.json"'
    )
    assert json.loads(response.content)["account"]["email"] == verified_user.email


def test_export_holds_only_the_own_data(api: AuthApi, verified_user: User) -> None:
    other = other_user()
    AthleteProfile.objects.create(owner=verified_user, timezone="Europe/Berlin", weight_kg=70)
    AthleteProfile.objects.create(owner=other, timezone="Asia/Tokyo", weight_kg=55)
    api.login(verified_user.email)

    body = api.call("GET", EXPORT).content.decode()

    assert "Europe/Berlin" in body
    assert other.email not in body
    assert "Asia/Tokyo" not in body


def test_delete_removes_the_account_and_ends_the_session(api: AuthApi, verified_user: User) -> None:
    other = other_user()
    AthleteProfile.objects.create(owner=verified_user, timezone="Europe/Berlin", weight_kg=70)
    AthleteProfile.objects.create(owner=other, timezone="Asia/Tokyo", weight_kg=55)
    api.login(verified_user.email)

    response = api.call("POST", DELETE, delete_body(verified_user))

    assert response.status_code == HTTPStatus.NO_CONTENT
    assert not User.objects.filter(pk=verified_user.pk).exists()
    assert not AthleteProfile.objects.filter(timezone="Europe/Berlin").exists()
    assert api.call("GET", "/api/me/").status_code == HTTPStatus.FORBIDDEN
    assert not api.is_authenticated
    assert api.login(verified_user.email).status_code != HTTPStatus.OK
    assert User.objects.filter(pk=other.pk).exists()
    assert AthleteProfile.objects.filter(owner=other).exists()


def test_delete_leaves_a_second_session_of_another_user_alone(
    api: AuthApi, verified_user: User
) -> None:
    other = other_user()
    other_api = AuthApi()
    other_api.login(other.email)
    api.login(verified_user.email)

    api.call("POST", DELETE, delete_body(verified_user))

    assert other_api.is_authenticated


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"confirmation": "someone@example.com"}, "confirmation"),
        ({"password": "wrong-password"}, "password"),
    ],
)
def test_delete_rejects_wrong_confirmation_or_password(
    api: AuthApi, verified_user: User, overrides: dict[str, str], field: str
) -> None:
    api.login(verified_user.email)

    response = api.call("POST", DELETE, {**delete_body(verified_user), **overrides})

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert field in response.json()
    assert User.objects.filter(pk=verified_user.pk).exists()
    assert api.is_authenticated


def test_delete_requires_all_fields(api: AuthApi, verified_user: User) -> None:
    api.login(verified_user.email)

    response = api.call("POST", DELETE, {})

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert set(response.json()) == {"confirmation", "password"}


def test_delete_with_an_authenticator_app_needs_a_code(
    api: AuthApi, verified_user: User, second_factor: SecondFactor
) -> None:
    api.login_with_totp(verified_user.email, second_factor.secret)

    missing = api.call("POST", DELETE, delete_body(verified_user))
    wrong = api.call("POST", DELETE, delete_body(verified_user, mfa_code="000000"))

    assert missing.status_code == HTTPStatus.BAD_REQUEST
    assert "mfa_code" in missing.json()
    assert wrong.status_code == HTTPStatus.BAD_REQUEST
    assert "mfa_code" in wrong.json()
    assert User.objects.filter(pk=verified_user.pk).exists()

    # The authenticator code was just used to sign in and cannot be replayed; a recovery works.
    ok = api.call(
        "POST", DELETE, delete_body(verified_user, mfa_code=second_factor.recovery_codes[0])
    )

    assert ok.status_code == HTTPStatus.NO_CONTENT
    assert not User.objects.filter(pk=verified_user.pk).exists()


def test_the_last_administrator_cannot_be_deleted(api: AuthApi, verified_staff: User) -> None:
    api.login(verified_staff.email)

    response = api.call("POST", DELETE, delete_body(verified_staff))

    assert response.status_code == HTTPStatus.CONFLICT
    assert response.json()["code"] == "last_admin"
    assert User.objects.filter(pk=verified_staff.pk).exists()
    assert api.is_authenticated


def test_an_administrator_can_be_deleted_when_another_remains(
    api: AuthApi, verified_staff: User
) -> None:
    User.objects.create_superuser("second-admin@example.com", PASSWORD)
    api.login(verified_staff.email)

    response = api.call("POST", DELETE, delete_body(verified_staff))

    assert response.status_code == HTTPStatus.NO_CONTENT


def test_export_is_rate_limited(api: AuthApi, verified_user: User) -> None:
    api.login(verified_user.email)

    statuses = [api.call("GET", EXPORT).status_code for _ in range(6)]

    assert statuses == [HTTPStatus.OK] * 5 + [HTTPStatus.TOO_MANY_REQUESTS]


def test_delete_is_rate_limited(api: AuthApi, verified_user: User) -> None:
    api.login(verified_user.email)
    wrong = {**delete_body(verified_user), "password": "wrong-password"}

    statuses = [api.call("POST", DELETE, wrong).status_code for _ in range(6)]

    assert statuses == [HTTPStatus.BAD_REQUEST] * 5 + [HTTPStatus.TOO_MANY_REQUESTS]
    assert User.objects.filter(pk=verified_user.pk).exists()
