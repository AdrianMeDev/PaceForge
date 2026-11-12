from typing import Self

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.db import models

from accounts.models import User


class OwnedQuerySet[T: models.Model](models.QuerySet[T]):
    def for_user(self, user: User | AnonymousUser) -> Self:
        """Restrict to the objects ``user`` owns. Anonymous users own nothing."""
        if not user.is_authenticated:
            return self.none()
        return self.filter(owner=user)


class OwnedModel(models.Model):
    """Base for every personal record. Each row belongs to exactly one user.

    Deleting the user deletes their data, which is what account deletion promises.
    Access always goes through ``for_user()``; never expose ``objects.all()`` to a request.
    """

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
        editable=False,
    )

    objects = OwnedQuerySet.as_manager()

    class Meta:
        abstract = True
