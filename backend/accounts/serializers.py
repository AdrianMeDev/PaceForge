from typing import Any

from rest_framework import serializers

from accounts.models import User, UserInvitation
from accounts.services.mfa import has_totp


class InvitationCreateSerializer(serializers.Serializer):
    email = serializers.EmailField()


class InvitationSerializer(serializers.ModelSerializer):
    status = serializers.CharField(read_only=True)

    class Meta:
        model = UserInvitation
        fields = ["id", "email", "status", "created_at", "expires_at"]
        read_only_fields = fields


class MeSerializer(serializers.ModelSerializer[User]):
    """The signed-in user. ``mfa_setup_required`` is true for administrators without TOTP."""

    class Meta:
        model = User
        fields = ["id", "email", "display_name", "is_staff"]
        read_only_fields = fields

    def to_representation(self, instance: User) -> dict[str, Any]:
        data = super().to_representation(instance)
        mfa_enabled = has_totp(instance)
        return {
            **data,
            "mfa_enabled": mfa_enabled,
            "mfa_setup_required": instance.is_staff and not mfa_enabled,
        }
