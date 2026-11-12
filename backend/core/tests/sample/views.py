from rest_framework import serializers

from accounts.models import User
from core.tests.sample.models import Note
from core.views import OwnedModelViewSet


class NoteSerializer(serializers.ModelSerializer[Note]):
    # `owner` is deliberately writable here: the base viewset must not let clients set it.
    owner = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), required=False)

    class Meta:
        model = Note
        fields = ["id", "title", "owner"]


class NoteViewSet(OwnedModelViewSet):
    queryset = Note.objects.all()
    serializer_class = NoteSerializer


class UnscopedViewSet(OwnedModelViewSet):
    """Misconfigured on purpose: its queryset does not come from an OwnedModel manager."""

    queryset = User.objects.all()
    serializer_class = NoteSerializer
