from http import HTTPStatus
from typing import TYPE_CHECKING

import pytest
from allauth.mfa.recovery_codes.internal.auth import RecoveryCodes

from accounts.models import User, UserInvitation
from accounts.services.invitations import create_invitation

from .conftest import AuthApi, enable_totp, totp_code

if TYPE_CHECKING:
    from django.test.client import _MonkeyPatchedWSGIResponse as HttpResponse

pytestmark = pytest.mark.django_db

INVITATIONS = "/api/admin/invitations/"
ME = "/api/me/"
TOTP_URL = "/account/authenticators/totp"


def revoke_url(user: User) -> str:
    created = create_invitation(invited_by=user, email="someone@example.com")
    return f"{INVITATIONS}{created.invitation.pk}/revoke/"


def admin_requests(api: AuthApi, user: User) -> dict[str, HttpResponse]:
    """One response per admin endpoint."""
    return {
        "list": api.call("GET", INVITATIONS),
        "create": api.call("POST", INVITATIONS, {"email": "new@example.com"}),
        "revoke": api.call("POST", revoke_url(user)),
    }


class TestAdministratorsNeedTwoFactorAuthentication:
    def test_an_administrator_without_totp_is_told_what_is_missing(
        self, api: AuthApi, verified_staff: User
    ) -> None:
        assert api.login(verified_staff.email).status_code == HTTPStatus.OK

        responses = admin_requests(api, verified_staff)

        for name, response in responses.items():
            assert response.status_code == HTTPStatus.FORBIDDEN, name
            body = response.json()
            assert body["code"] == "mfa_required", name
            assert "Two-factor authentication" in body["detail"], name
        assert UserInvitation.objects.filter(email="new@example.com").count() == 0

    def test_recovery_codes_alone_do_not_open_the_admin_api(
        self, api: AuthApi, verified_staff: User
    ) -> None:
        RecoveryCodes.activate(verified_staff)
        assert api.login(verified_staff.email).status_code == HTTPStatus.OK

        response = api.call("GET", INVITATIONS)

        assert response.status_code == HTTPStatus.FORBIDDEN
        assert response.json()["code"] == "mfa_required"

    def test_an_administrator_with_totp_has_access(
        self, api: AuthApi, verified_staff: User
    ) -> None:
        factor = enable_totp(verified_staff)
        assert api.login_with_totp(verified_staff.email, factor.secret).status_code == 200

        assert api.call("GET", INVITATIONS).status_code == HTTPStatus.OK
        created = api.call("POST", INVITATIONS, {"email": "new@example.com"})
        assert created.status_code == HTTPStatus.CREATED
        revoke = f"{INVITATIONS}{created.json()['id']}/revoke/"
        assert api.call("POST", revoke).status_code == HTTPStatus.OK

    def test_setting_up_totp_in_the_same_session_opens_the_admin_api(
        self, api: AuthApi, verified_staff: User
    ) -> None:
        api.login(verified_staff.email)
        assert api.call("GET", INVITATIONS).status_code == HTTPStatus.FORBIDDEN

        secret = api.request("GET", TOTP_URL).json()["meta"]["secret"]
        api.reauthenticate()
        api.request("POST", TOTP_URL, {"code": totp_code(secret)})

        assert api.call("GET", INVITATIONS).status_code == HTTPStatus.OK

    def test_turning_totp_off_closes_the_admin_api_again(
        self, api: AuthApi, verified_staff: User
    ) -> None:
        factor = enable_totp(verified_staff)
        api.login_with_totp(verified_staff.email, factor.secret)
        assert api.call("GET", INVITATIONS).status_code == HTTPStatus.OK

        api.reauthenticate()
        api.request("DELETE", TOTP_URL)

        response = api.call("GET", INVITATIONS)
        assert response.status_code == HTTPStatus.FORBIDDEN
        assert response.json()["code"] == "mfa_required"


class TestOthersAreNotTold:
    def test_members_get_the_plain_refusal_even_with_totp(
        self, api: AuthApi, verified_user: User
    ) -> None:
        factor = enable_totp(verified_user)
        api.login_with_totp(verified_user.email, factor.secret)

        response = api.call("GET", INVITATIONS)

        assert response.status_code == HTTPStatus.FORBIDDEN
        assert "code" not in response.json()

    def test_members_without_totp_get_the_plain_refusal(
        self, api: AuthApi, verified_user: User
    ) -> None:
        api.login(verified_user.email)

        response = api.call("POST", INVITATIONS, {"email": "new@example.com"})

        assert response.status_code == HTTPStatus.FORBIDDEN
        assert "code" not in response.json()

    def test_anonymous_visitors_get_the_plain_refusal(self, api: AuthApi) -> None:
        response = api.call("GET", INVITATIONS)

        assert response.status_code == HTTPStatus.FORBIDDEN
        assert "code" not in response.json()


class TestWhatTheAccountEndpointReports:
    def flags(self, api: AuthApi) -> tuple[bool, bool]:
        body = api.call("GET", ME).json()
        return body["mfa_enabled"], body["mfa_setup_required"]

    def test_member_without_totp(self, api: AuthApi, verified_user: User) -> None:
        api.login(verified_user.email)

        assert self.flags(api) == (False, False)

    def test_member_with_totp(self, api: AuthApi, verified_user: User) -> None:
        factor = enable_totp(verified_user)
        api.login_with_totp(verified_user.email, factor.secret)

        assert self.flags(api) == (True, False)

    def test_administrator_without_totp_has_to_set_it_up(
        self, api: AuthApi, verified_staff: User
    ) -> None:
        api.login(verified_staff.email)

        assert self.flags(api) == (False, True)

    def test_administrator_with_totp(self, api: AuthApi, verified_staff: User) -> None:
        factor = enable_totp(verified_staff)
        api.login_with_totp(verified_staff.email, factor.secret)

        assert self.flags(api) == (True, False)

    def test_recovery_codes_alone_do_not_count_as_enabled(
        self, api: AuthApi, verified_staff: User
    ) -> None:
        RecoveryCodes.activate(verified_staff)
        api.login(verified_staff.email)

        assert self.flags(api) == (False, True)

    def test_the_flags_follow_a_setup_made_in_the_same_session(
        self, api: AuthApi, verified_staff: User
    ) -> None:
        api.login(verified_staff.email)
        secret = api.request("GET", TOTP_URL).json()["meta"]["secret"]
        api.reauthenticate()
        api.request("POST", TOTP_URL, {"code": totp_code(secret)})

        assert self.flags(api) == (True, False)
