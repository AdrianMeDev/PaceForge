from rest_framework import serializers

from accounts.models import User
from core.tests.sample.models import Note
from core.views import OwnedModelViewSet


class NoteSerializer(serializers.ModelSerializer[Note]):
    class Meta:
        model = Note
        fields = ["id", "title", "owner"]
        read_only_fields = ["owner"]


class NoteViewSet(OwnedModelViewSet):
    queryset = Note.objects.all()
    serializer_class = NoteSerializer


class WritableOwnerNoteSerializer(serializers.ModelSerializer[Note]):
    """Misconfigured on purpose: exposes a writable ``owner`` field over ``User.objects.all()``."""

    owner = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), required=False)

    class Meta:
        model = Note
        fields = ["id", "title", "owner"]


class WritableOwnerNoteViewSet(OwnedModelViewSet):
    """Fixture viewset using ``WritableOwnerNoteSerializer`` to test server-side owner override."""

    queryset = Note.objects.all()
    serializer_class = WritableOwnerNoteSerializer


class UnscopedViewSet(OwnedModelViewSet):
    """Misconfigured on purpose: its queryset does not come from an OwnedModel manager."""

    queryset = User.objects.all()
    serializer_class = NoteSerializer
