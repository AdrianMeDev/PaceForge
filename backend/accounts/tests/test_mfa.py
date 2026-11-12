from http import HTTPStatus
from urllib.parse import parse_qs, unquote, urlparse

import pytest
from allauth.mfa.models import Authenticator

from accounts.models import User

from .conftest import AuthApi, SecondFactor, totp_code

pytestmark = pytest.mark.django_db

TOTP_URL = "/account/authenticators/totp"
RECOVERY_URL = "/account/authenticators/recovery-codes"


def error_codes(response) -> set[tuple[str, str]]:
    return {(error["param"], error["code"]) for error in response.json()["errors"]}


def pending_flow_ids(response) -> set[str]:
    return {flow["id"] for flow in response.json()["data"]["flows"] if flow.get("is_pending")}


def needs_reauthentication(response) -> bool:
    body = response.json()
    flows = {flow["id"] for flow in body["data"]["flows"]}
    return (
        response.status_code == HTTPStatus.UNAUTHORIZED
        and body["meta"]["is_authenticated"] is True
        and "reauthenticate" in flows
    )


def types_of(user: User) -> list[str]:
    return sorted(Authenticator.objects.filter(user=user).values_list("type", flat=True))


class TestSigningInWithASecondFactor:
    def test_password_alone_leaves_the_sign_in_pending(
        self, api: AuthApi, verified_user: User, second_factor: SecondFactor
    ) -> None:
        response = api.login(verified_user.email)

        assert response.status_code == HTTPStatus.UNAUTHORIZED
        assert pending_flow_ids(response) == {"mfa_authenticate"}
        mfa_flow = next(
            f for f in response.json()["data"]["flows"] if f["id"] == "mfa_authenticate"
        )
        assert set(mfa_flow["types"]) == {"totp", "recovery_codes"}
        assert not api.is_authenticated

    def test_a_valid_code_completes_the_sign_in(
        self, api: AuthApi, verified_user: User, second_factor: SecondFactor
    ) -> None:
        api.login(verified_user.email)

        response = api.authenticate_mfa(totp_code(second_factor.secret))

        assert response.status_code == HTTPStatus.OK
        assert api.is_authenticated

    def test_a_wrong_code_is_rejected(
        self, api: AuthApi, verified_user: User, second_factor: SecondFactor
    ) -> None:
        api.login(verified_user.email)

        response = api.authenticate_mfa("000000")

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert ("code", "incorrect_code") in error_codes(response)
        assert not api.is_authenticated

    def test_a_code_cannot_be_used_twice(
        self, api: AuthApi, verified_user: User, second_factor: SecondFactor
    ) -> None:
        code = totp_code(second_factor.secret)
        api.login(verified_user.email)
        assert api.authenticate_mfa(code).status_code == HTTPStatus.OK
        api.request("DELETE", "/auth/session")

        api.login(verified_user.email)
        replay = api.authenticate_mfa(code)

        assert replay.status_code == HTTPStatus.BAD_REQUEST
        assert not api.is_authenticated

    def test_a_recovery_code_works_once(
        self, api: AuthApi, verified_user: User, second_factor: SecondFactor
    ) -> None:
        recovery_code = second_factor.recovery_codes[0]
        api.login(verified_user.email)
        assert api.authenticate_mfa(recovery_code).status_code == HTTPStatus.OK
        api.request("DELETE", "/auth/session")

        api.login(verified_user.email)

        assert api.authenticate_mfa(recovery_code).status_code == HTTPStatus.BAD_REQUEST
        assert api.authenticate_mfa(second_factor.recovery_codes[1]).status_code == HTTPStatus.OK

    def test_repeated_wrong_codes_lock_the_sign_in_even_for_the_right_code(
        self, api: AuthApi, verified_user: User, second_factor: SecondFactor
    ) -> None:
        api.login(verified_user.email)
        for _ in range(5):
            assert api.authenticate_mfa("000000").status_code == HTTPStatus.BAD_REQUEST

        response = api.authenticate_mfa(totp_code(second_factor.secret))

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert ("code", "too_many_login_attempts") in error_codes(response)
        assert not api.is_authenticated

    def test_accounts_without_a_second_factor_sign_in_as_before(
        self, api: AuthApi, verified_user: User
    ) -> None:
        assert api.login(verified_user.email).status_code == HTTPStatus.OK


class TestSettingUpTotp:
    def test_the_setup_offers_a_secret_and_an_authenticator_url(
        self, api: AuthApi, verified_user: User
    ) -> None:
        api.login(verified_user.email)

        response = api.request("GET", TOTP_URL)

        assert response.status_code == HTTPStatus.NOT_FOUND  # allauth: "no authenticator yet"
        meta = response.json()["meta"]
        url = urlparse(meta["totp_url"])
        query = parse_qs(url.query)
        assert url.scheme == "otpauth"
        assert url.netloc == "totp"
        assert unquote(url.path) == f"/{verified_user.email}"
        assert query["issuer"] == ["PaceForge"]
        assert query["secret"] == [meta["secret"]]

    def test_activation_asks_for_the_password_first(
        self, api: AuthApi, verified_user: User
    ) -> None:
        api.login(verified_user.email)
        secret = api.request("GET", TOTP_URL).json()["meta"]["secret"]

        response = api.request("POST", TOTP_URL, {"code": totp_code(secret)})

        assert needs_reauthentication(response)
        assert types_of(verified_user) == []

    def test_a_wrong_password_does_not_count_as_confirmation(
        self, api: AuthApi, verified_user: User
    ) -> None:
        api.login(verified_user.email)

        response = api.reauthenticate("not-the-password")

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert ("password", "incorrect_password") in error_codes(response)

    def test_activation_with_a_wrong_code_is_rejected(
        self, api: AuthApi, verified_user: User
    ) -> None:
        api.login(verified_user.email)
        api.request("GET", TOTP_URL)
        api.reauthenticate()

        response = api.request("POST", TOTP_URL, {"code": "000000"})

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert ("code", "incorrect_code") in error_codes(response)
        assert types_of(verified_user) == []

    def test_activation_creates_the_authenticator_and_ten_recovery_codes(
        self, api: AuthApi, verified_user: User
    ) -> None:
        api.login(verified_user.email)
        secret = api.request("GET", TOTP_URL).json()["meta"]["secret"]
        api.reauthenticate()

        response = api.request("POST", TOTP_URL, {"code": totp_code(secret)})

        assert response.status_code == HTTPStatus.OK
        assert response.json()["data"]["type"] == "totp"
        assert types_of(verified_user) == ["recovery_codes", "totp"]
        codes = api.request("GET", RECOVERY_URL).json()["data"]
        assert codes["total_code_count"] == codes["unused_code_count"] == 10
        assert len(codes["unused_codes"]) == 10

    def test_the_new_authenticator_is_required_at_the_next_sign_in(
        self, api: AuthApi, verified_user: User
    ) -> None:
        api.login(verified_user.email)
        secret = api.request("GET", TOTP_URL).json()["meta"]["secret"]
        api.reauthenticate()
        api.request("POST", TOTP_URL, {"code": totp_code(secret)})
        api.request("DELETE", "/auth/session")

        response = api.login(verified_user.email)

        assert pending_flow_ids(response) == {"mfa_authenticate"}

    def test_the_list_of_authenticators_shows_both_kinds(
        self, api: AuthApi, verified_user: User, second_factor: SecondFactor
    ) -> None:
        api.login_with_totp(verified_user.email, second_factor.secret)

        response = api.request("GET", "/account/authenticators")

        assert {item["type"] for item in response.json()["data"]} == {"totp", "recovery_codes"}


class TestManagingTheSecondFactor:
    def test_turning_it_off_needs_the_password_and_then_works(
        self, api: AuthApi, verified_user: User, second_factor: SecondFactor
    ) -> None:
        api.login_with_totp(verified_user.email, second_factor.secret)

        assert needs_reauthentication(api.request("DELETE", TOTP_URL))
        assert "totp" in types_of(verified_user)
        api.reauthenticate()
        assert api.request("DELETE", TOTP_URL).status_code == HTTPStatus.OK

        assert "totp" not in types_of(verified_user)
        api.request("DELETE", "/auth/session")
        assert (
            api.login(verified_user.email).status_code == HTTPStatus.OK
        )  # no second step any more

    def test_new_recovery_codes_replace_the_old_ones(
        self, api: AuthApi, verified_user: User, second_factor: SecondFactor
    ) -> None:
        api.login_with_totp(verified_user.email, second_factor.secret)

        assert needs_reauthentication(api.request("POST", RECOVERY_URL, {}))
        api.reauthenticate()
        response = api.request("POST", RECOVERY_URL, {})

        assert response.status_code == HTTPStatus.OK
        fresh = api.request("GET", RECOVERY_URL).json()["data"]["unused_codes"]
        assert len(fresh) == 10
        assert not set(fresh) & set(second_factor.recovery_codes)
        api.request("DELETE", "/auth/session")
        api.login(verified_user.email)
        assert api.authenticate_mfa(second_factor.recovery_codes[0]).status_code == 400
        assert api.authenticate_mfa(fresh[0]).status_code == HTTPStatus.OK

    def test_viewing_the_recovery_codes_needs_the_password(
        self, api: AuthApi, verified_user: User, second_factor: SecondFactor
    ) -> None:
        api.login_with_totp(verified_user.email, second_factor.secret)

        assert needs_reauthentication(api.request("GET", RECOVERY_URL))
        api.reauthenticate()
        shown = api.request("GET", RECOVERY_URL).json()["data"]["unused_codes"]

        assert sorted(shown) == sorted(second_factor.recovery_codes)


class TestWhatIsOffered:
    def test_only_totp_and_recovery_codes_are_supported(self, api: AuthApi) -> None:
        mfa = api.request("GET", "/config").json()["data"]["mfa"]

        assert set(mfa["supported_types"]) == {"totp", "recovery_codes"}
        assert mfa["passkey_login_enabled"] is False

    def test_there_is_no_webauthn_endpoint(self, api: AuthApi, verified_user: User) -> None:
        api.login(verified_user.email)

        assert api.request("GET", "/account/authenticators/webauthn").status_code == 404
        assert api.request("POST", "/auth/webauthn/login").status_code == 404
