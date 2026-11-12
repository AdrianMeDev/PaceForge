from django.db import models

from core.fields import EncryptedTextField
from core.models import OwnedModel


class Note(OwnedModel):
    title = models.CharField(max_length=100)


class Credential(models.Model):
    """Carries an ``EncryptedTextField`` for the field tests."""

    label = models.CharField(max_length=50, blank=True)
    secret = EncryptedTextField(null=True, blank=True)

    def __str__(self) -> str:
        return self.label
