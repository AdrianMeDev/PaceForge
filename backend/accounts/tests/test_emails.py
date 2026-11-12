from http import HTTPStatus

import pytest
from allauth.account.adapter import DefaultAccountAdapter
from django.core import mail

from accounts.models import User

from .conftest import AuthApi

pytestmark = pytest.mark.django_db

SIGNUP_LINK = "/account/signup"


def request_reset(api: AuthApi, email: str):
    return api.request("POST", "/auth/password/request", {"email": email})


class TestUnknownAccountMail:
    def sent_to_unknown_address(self, api: AuthApi) -> mail.EmailMessage:
        request_reset(api, "nobody@example.com")
        [message] = mail.outbox
        return message

    @pytest.mark.parametrize("mode", ["invite_only", "closed"])
    def test_without_open_registration_it_does_not_point_to_a_signup_page(
        self, api: AuthApi, settings, mode: str
    ) -> None:
        settings.REGISTRATION_MODE = mode

        message = self.sent_to_unknown_address(api)

        assert SIGNUP_LINK not in message.body
        assert "sign up" not in message.body.lower()

    def test_in_invite_only_mode_it_says_to_ask_for_an_invitation(
        self, api: AuthApi, settings
    ) -> None:
        settings.REGISTRATION_MODE = "invite_only"

        body = self.sent_to_unknown_address(api).body

        assert "created by invitation" in body
        assert "ask an administrator to invite you" in body

    def test_in_closed_mode_it_says_that_there_are_no_new_accounts(
        self, api: AuthApi, settings
    ) -> None:
        settings.REGISTRATION_MODE = "closed"

        body = self.sent_to_unknown_address(api).body

        assert "cannot be created" in body
        assert "invitation" not in body

    def test_in_open_mode_it_still_links_to_the_signup_page(self, api: AuthApi, settings) -> None:
        settings.REGISTRATION_MODE = "open"

        body = self.sent_to_unknown_address(api).body

        assert f"http://testserver{SIGNUP_LINK}" in body
        assert "invitation" not in body

    def test_it_still_names_the_address_and_can_be_ignored(self, api: AuthApi) -> None:
        message = self.sent_to_unknown_address(api)

        assert "nobody@example.com" in message.body
        assert "can be safely ignored" in message.body
        assert message.to == ["nobody@example.com"]

    def test_the_subject_and_the_frame_of_the_mail_are_unchanged(self, api: AuthApi) -> None:
        message = self.sent_to_unknown_address(api)

        assert "Unknown Account" in message.subject
        assert message.body.startswith("Hello from")
        assert "Thank you for using" in message.body

    def test_the_answer_does_not_reveal_whether_the_address_has_an_account(
        self, api: AuthApi, verified_user: User
    ) -> None:
        known = request_reset(api, verified_user.email)
        unknown = request_reset(AuthApi(), "nobody@example.com")

        assert known.status_code == unknown.status_code == HTTPStatus.OK
        assert known.json() == unknown.json()


class TestOtherMailsAreNotAffected:
    def test_a_reset_mail_for_a_known_address_has_its_link_and_no_registration_text(
        self, api: AuthApi, verified_user: User
    ) -> None:
        request_reset(api, verified_user.email)

        [message] = mail.outbox
        assert "/account/password/reset/key/" in message.body
        assert "invitation" not in message.body
        assert SIGNUP_LINK not in message.body

    def test_every_mail_gets_the_registration_mode_in_its_context(
        self, api: AuthApi, settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings.REGISTRATION_MODE = "closed"
        seen: list[dict] = []
        original = DefaultAccountAdapter.render_mail

        def spy(self, template_prefix, email, context, *args, **kwargs):
            seen.append(context)
            return original(self, template_prefix, email, context, *args, **kwargs)

        monkeypatch.setattr(DefaultAccountAdapter, "render_mail", spy)

        request_reset(api, "nobody@example.com")

        assert [c["registration_mode"] for c in seen] == ["closed"]
