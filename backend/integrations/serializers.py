from typing import Any

from rest_framework import serializers

from integrations.models import ProviderConnection


class StringField(serializers.CharField):
    """A text field that does not turn numbers into text: a key must be sent as a string."""

    def to_internal_value(self, data: Any) -> str:
        if not isinstance(data, str):
            self.fail("invalid")
        return super().to_internal_value(data)


class ConnectSerializer(serializers.Serializer):
    # Write-only by construction: this serializer is only ever used to read input.
    api_key = StringField(max_length=200, trim_whitespace=True, write_only=True)


class ConnectionSerializer(serializers.ModelSerializer[ProviderConnection]):
    """The state of a connection. The key is never part of it, not even in part."""

    class Meta:
        model = ProviderConnection
        fields = ["status", "athlete_id", "connected_at", "last_checked_at"]
        read_only_fields = fields

    def to_representation(self, instance: ProviderConnection) -> dict[str, Any]:
        return {"connected": True, **super().to_representation(instance)}
