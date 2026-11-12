from typing import Any

from django import forms
from django.conf import settings
from django.http import HttpRequest

from accounts.services.invitations import InvalidInvitationError, get_valid_invitation


class InvitationSignupForm(forms.Form):
    """Extra field of the allauth signup form (ACCOUNT_SIGNUP_FORM_CLASS).

    The invitation is only validated here; it is consumed together with creating the user
    in ``AccountAdapter.save_user`` so that a rejected signup never burns an invitation.
    """

    invitation_token = forms.CharField(required=False, strip=True)

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean() or self.cleaned_data
        if settings.REGISTRATION_MODE != "invite_only" or self.errors:
            return cleaned_data
        token = cleaned_data.get("invitation_token")
        try:
            if not token:
                raise InvalidInvitationError
            get_valid_invitation(token, email=cleaned_data.get("email"))
        except InvalidInvitationError:
            self.add_error(
                "invitation_token",
                forms.ValidationError(
                    "A valid invitation for this email address is required.",
                    code="invalid_invitation",
                ),
            )
        return cleaned_data

    def signup(self, request: HttpRequest, user: Any) -> None:
        """Hook required by allauth; the invitation is consumed in the adapter."""
