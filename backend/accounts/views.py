import json
from typing import Any

from django.contrib.auth import logout
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import Throttled, ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User, UserInvitation
from accounts.permissions import IsMfaAdmin
from accounts.serializers import (
    AccountDeleteSerializer,
    InvitationCreateSerializer,
    InvitationSerializer,
    MeSerializer,
)
from accounts.services.deletion import (
    AccountDeletionError,
    ConfirmationMismatchError,
    InvalidMfaCodeError,
    InvalidPasswordError,
    LastAdminError,
    MfaRequiredError,
    delete_account,
)
from accounts.services.export import build_user_export
from accounts.services.invitation_limits import InvitationLimitError, reserve_invitation_email
from accounts.services.invitations import (
    CreatedInvitation,
    Delivery,
    InvalidInvitationError,
    build_invitation_url,
    create_invitation,
    resend_invitation,
    revoke_invitation,
    send_invitation_email,
)
from accounts.throttles import (
    AccountDeleteThrottle,
    AccountExportThrottle,
)


def _delivery_data(created: CreatedInvitation) -> dict[str, Any]:
    """Mail the signup link and describe the result for the admin.

    The link is returned too: it is the only time the plaintext token leaves the server, and the
    admin can hand it on by other means when the mail did not go out.
    """
    delivery = send_invitation_email(created)
    invite_url = build_invitation_url(token=created.token, email=created.invitation.email)
    return {
        **InvitationSerializer(created.invitation).data,
        "invite_url": invite_url,
        "delivery": delivery,
        "email_sent": delivery == Delivery.SENT,
    }


class InvitationListCreateView(APIView):
    """Administrators with two-factor authentication: list invitations and create new ones."""

    permission_classes = [IsMfaAdmin]

    def get(self, request: Request) -> Response:
        invitations = UserInvitation.objects.order_by("-created_at")
        return Response(InvitationSerializer(invitations, many=True).data)

    def post(self, request: Request) -> Response:
        serializer = InvitationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        assert isinstance(request.user, User)  # IsMfaAdmin guarantees an authenticated user
        try:
            reserve_invitation_email(
                sender=request.user, recipient=serializer.validated_data["email"]
            )
        except InvitationLimitError as error:
            raise Throttled(wait=error.retry_after) from error
        created = create_invitation(
            invited_by=request.user, email=serializer.validated_data["email"]
        )
        return Response(_delivery_data(created), status=status.HTTP_201_CREATED)


class InvitationResendView(APIView):
    """Issue a new link for a pending or expired invitation and mail it again."""

    permission_classes = [IsMfaAdmin]

    def post(self, request: Request, pk: str) -> Response:
        invitation = get_object_or_404(UserInvitation, pk=pk)
        assert isinstance(request.user, User)  # IsMfaAdmin guarantees an authenticated user
        try:
            reserve_invitation_email(sender=request.user, recipient=invitation.email)
        except InvitationLimitError as error:
            raise Throttled(wait=error.retry_after) from error
        try:
            created = resend_invitation(invitation)
        except InvalidInvitationError:
            return Response(
                {"detail": "A used or revoked invitation cannot be sent again."},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(_delivery_data(created))


class InvitationRevokeView(APIView):
    permission_classes = [IsMfaAdmin]

    def post(self, request: Request, pk: str) -> Response:
        invitation = get_object_or_404(UserInvitation, pk=pk)
        try:
            revoke_invitation(invitation)
        except InvalidInvitationError:
            return Response(
                {"detail": "A used invitation cannot be revoked."}, status=status.HTTP_409_CONFLICT
            )
        return Response(InvitationSerializer(invitation).data)


class MeView(APIView):
    """The authenticated user's own account data; nothing else is ever returned here."""

    def get(self, request: Request) -> Response:
        assert isinstance(request.user, User)  # IsAuthenticated is the default permission
        return Response(MeSerializer(request.user).data)


class AccountExportView(APIView):
    """Everything stored about the signed-in user, as a JSON file to download."""

    throttle_classes = [AccountExportThrottle]

    def get(self, request: Request) -> HttpResponse:
        assert isinstance(request.user, User)  # IsAuthenticated is the default permission
        data = build_user_export(request.user)
        filename = f"paceforge-export-{timezone.localdate().isoformat()}.json"
        response = HttpResponse(
            json.dumps(data, indent=2, ensure_ascii=False),
            content_type="application/json",
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        response["Cache-Control"] = "no-store"
        return response


# Fixed texts: nothing of the request goes into an error.
DELETE_ERRORS: dict[type[AccountDeletionError], tuple[str, str]] = {
    ConfirmationMismatchError: ("confirmation", "The email does not match this account."),
    InvalidPasswordError: ("password", "The password is wrong."),
    MfaRequiredError: ("mfa_code", "A code from your authenticator app is required."),
    InvalidMfaCodeError: ("mfa_code", "The code is not valid."),
}


class AccountDeleteView(APIView):
    """Deletes the signed-in account and all its data, and ends the session."""

    throttle_classes = [AccountDeleteThrottle]

    def post(self, request: Request) -> Response:
        assert isinstance(request.user, User)  # IsAuthenticated is the default permission
        serializer = AccountDeleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            delete_account(
                request.user,
                password=serializer.validated_data["password"],
                confirmation=serializer.validated_data["confirmation"],
                mfa_code=serializer.validated_data.get("mfa_code", ""),
            )
        except LastAdminError:
            return Response(
                {
                    "detail": "The last administrator cannot be deleted.",
                    "code": "last_admin",
                },
                status=status.HTTP_409_CONFLICT,
            )
        except AccountDeletionError as error:
            field, message = DELETE_ERRORS[type(error)]
            raise ValidationError({field: [message]}) from error
        logout(request._request)
        return Response(status=status.HTTP_204_NO_CONTENT)
