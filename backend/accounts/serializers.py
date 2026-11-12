from rest_framework import serializers

from accounts.models import User, UserInvitation


class InvitationCreateSerializer(serializers.Serializer):
    email = serializers.EmailField()


class InvitationSerializer(serializers.ModelSerializer):
    status = serializers.CharField(read_only=True)

    class Meta:
        model = UserInvitation
        fields = ["id", "email", "status", "created_at", "expires_at"]
        read_only_fields = fields


class MeSerializer(serializers.ModelSerializer[User]):
    class Meta:
        model = User
        fields = ["id", "email", "display_name", "is_staff"]
        read_only_fields = fields
