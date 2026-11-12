from urllib.parse import urlencode

from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAdminUser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import UserInvitation
from accounts.serializers import InvitationCreateSerializer, InvitationSerializer
from accounts.services.invitations import (
    InvalidInvitationError,
    create_invitation,
    revoke_invitation,
)


class InvitationListCreateView(APIView):
    """Staff-only: list invitations and create new ones."""

    permission_classes = [IsAdminUser]

    def get(self, request: Request) -> Response:
        invitations = UserInvitation.objects.order_by("-created_at")
        return Response(InvitationSerializer(invitations, many=True).data)

    def post(self, request: Request) -> Response:
        serializer = InvitationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        created = create_invitation(
            invited_by=request.user, email=serializer.validated_data["email"]
        )
        signup_path = settings.HEADLESS_FRONTEND_URLS["account_signup"]
        invite_url = request.build_absolute_uri(
            f"{signup_path}?{urlencode({'invitation': created.token})}"
        )
        # The only time the plaintext token leaves the server: the admin hands the link on.
        data = {**InvitationSerializer(created.invitation).data, "invite_url": invite_url}
        return Response(data, status=status.HTTP_201_CREATED)


class InvitationRevokeView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request: Request, pk: str) -> Response:
        invitation = get_object_or_404(UserInvitation, pk=pk)
        try:
            revoke_invitation(invitation)
        except InvalidInvitationError:
            return Response(
                {"detail": "A used invitation cannot be revoked."}, status=status.HTTP_409_CONFLICT
            )
        return Response(InvitationSerializer(invitation).data)
