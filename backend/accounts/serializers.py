from rest_framework import serializers

from accounts.models import UserInvitation


class InvitationCreateSerializer(serializers.Serializer):
    email = serializers.EmailField()


class InvitationSerializer(serializers.ModelSerializer):
    status = serializers.CharField(read_only=True)

    class Meta:
        model = UserInvitation
        fields = ["id", "email", "status", "created_at", "expires_at"]
        read_only_fields = fields
