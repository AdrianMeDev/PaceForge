from django.db import models
from django.utils import timezone

from core.fields import EncryptedTextField
from core.models import OwnedModel


class ProviderConnection(OwnedModel):
    """A user's connection to one external training platform.

    ``api_key`` is the user's personal key for that platform. It is stored encrypted, cannot be
    edited through forms (``editable=False``) and must never be part of a serializer or a log
    line; the API only tells whether a connection exists and in which state it is.

    Django skips the validation of non-editable fields, so ``full_clean()`` does not reject an
    empty key: check it where the key is entered (the serializer of the connect endpoint).
    """

    class Provider(models.TextChoices):
        INTERVALS_ICU = "intervals_icu", "Intervals.icu"

    class Status(models.TextChoices):
        CONNECTED = "connected"
        INVALID = "invalid"  # the provider refused the stored key at the last check

    provider = models.CharField(max_length=30, choices=Provider.choices)
    api_key = EncryptedTextField(editable=False)
    # The account's id at the provider, so that the user can see which account is connected.
    athlete_id = models.CharField(max_length=50)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.CONNECTED)
    connected_at = models.DateTimeField(default=timezone.now)
    last_checked_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "provider"], name="integrations_one_connection_per_provider"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_provider_display()} connection of user {self.owner_id} ({self.status})"
