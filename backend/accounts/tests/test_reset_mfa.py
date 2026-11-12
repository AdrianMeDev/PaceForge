from http import HTTPStatus
from io import StringIO

import pytest
from allauth.account.models import EmailAddress
from allauth.mfa.models import Authenticator
from allauth.mfa.recovery_codes.internal.auth import RecoveryCodes
from django.core.management import call_command
from django.core.management.base import CommandError

from accounts.models import User

from .conftest import AuthApi, enable_totp

pytestmark = pytest.mark.django_db


def run(**options: object) -> str:
    out = StringIO()
    call_command("reset_mfa", stdout=out, **options)
    return out.getvalue()


def types_of(user: User) -> list[str]:
    return sorted(Authenticator.objects.filter(user=user).values_list("type", flat=True))


def test_the_account_signs_in_with_the_password_alone_afterwards(
    api: AuthApi, verified_user: User
) -> None:
    enable_totp(verified_user)
    flows = api.login(verified_user.email).json()["data"]["flows"]
    assert {f["id"] for f in flows if f.get("is_pending")} == {"mfa_authenticate"}
    api.request("DELETE", "/auth/session")

    output = run(email=verified_user.email)

    assert types_of(verified_user) == []
    assert api.login(verified_user.email).status_code == HTTPStatus.OK
    assert "password alone" in output


def test_an_administrator_is_told_to_set_it_up_again(api: AuthApi, verified_staff: User) -> None:
    enable_totp(verified_staff)

    run(email=verified_staff.email)

    api.login(verified_staff.email)
    flags = api.call("GET", "/api/me/").json()
    assert (flags["mfa_enabled"], flags["mfa_setup_required"]) == (False, True)


def test_it_says_what_was_removed(verified_user: User) -> None:
    enable_totp(verified_user)

    output = run(email=verified_user.email)

    assert "recovery_codes, totp" in output


def test_recovery_codes_alone_are_removed_too(verified_user: User) -> None:
    RecoveryCodes.activate(verified_user)

    output = run(email=verified_user.email)

    assert types_of(verified_user) == []
    assert "recovery_codes" in output


def test_other_accounts_keep_their_second_factor(verified_user: User, verified_staff: User) -> None:
    enable_totp(verified_user)
    enable_totp(verified_staff)

    run(email=verified_user.email)

    assert types_of(verified_user) == []
    assert types_of(verified_staff) == ["recovery_codes", "totp"]


def test_the_account_itself_is_left_alone(verified_user: User) -> None:
    enable_totp(verified_user)
    password_hash = verified_user.password

    run(email=verified_user.email)

    verified_user.refresh_from_db()
    assert verified_user.password == password_hash
    assert verified_user.is_active
    assert EmailAddress.objects.get(user=verified_user).verified


def test_the_email_is_matched_without_regard_to_case_and_spaces(verified_user: User) -> None:
    enable_totp(verified_user)

    run(email="  ATHLETE@Example.COM ")

    assert types_of(verified_user) == []


def test_running_it_twice_is_harmless(verified_user: User) -> None:
    enable_totp(verified_user)
    run(email=verified_user.email)

    output = run(email=verified_user.email)

    assert "nothing was changed" in output
    assert User.objects.filter(pk=verified_user.pk).exists()


def test_an_account_that_never_had_a_second_factor_is_not_changed(verified_user: User) -> None:
    output = run(email=verified_user.email)

    assert "nothing was changed" in output
    assert types_of(verified_user) == []


def test_an_unknown_address_is_an_error() -> None:
    with pytest.raises(CommandError, match="no account with the email nobody@example.com"):
        run(email="nobody@example.com")


def test_the_address_is_required() -> None:
    with pytest.raises(CommandError, match="--email"):
        run()
