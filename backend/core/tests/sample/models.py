from django.db import models

from core.models import OwnedModel


class Note(OwnedModel):
    title = models.CharField(max_length=100)
