from typing import Any

from allauth.account.adapter import DefaultAccountAdapter
from allauth.core.exceptions import ImmediateHttpResponse
from django.conf import settings
from django.db import transaction
from django.http import HttpRequest, JsonResponse

from accounts.services.invitations import InvalidInvitationError, consume_invitation


class AccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request: HttpRequest) -> bool:
        return settings.REGISTRATION_MODE != "closed"

    def save_user(self, request: HttpRequest, user: Any, form: Any, commit: bool = True) -> Any:
        if settings.REGISTRATION_MODE != "invite_only":
            return super().save_user(request, user, form, commit)

        # Creating the user and consuming the invitation succeed or fail together.
        with transaction.atomic():
            user = super().save_user(request, user, form, commit)
            try:
                consume_invitation(
                    form.cleaned_data.get("invitation_token", ""), user=user, email=user.email
                )
            except InvalidInvitationError:
                # Lost a race against another signup using the same token; leaving the atomic
                # block with an exception rolls the new user back.
                raise ImmediateHttpResponse(
                    JsonResponse(
                        {
                            "status": 400,
                            "errors": [
                                {
                                    "message": "This invitation is no longer valid.",
                                    "code": "invalid_invitation",
                                    "param": "invitation_token",
                                }
                            ],
                        },
                        status=400,
                    )
                ) from None
        return user
