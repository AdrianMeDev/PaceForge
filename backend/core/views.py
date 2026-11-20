from typing import Any

from django.core.exceptions import ImproperlyConfigured
from django.db.models import QuerySet
from rest_framework import viewsets
from rest_framework.exceptions import NotAuthenticated
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.serializers import BaseSerializer

from accounts.models import User
from core.models import OwnedQuerySet
from core.permissions import IsOwner


def authenticated_user(request: Request) -> User:
    """Return the authenticated ``User`` for ``request`` or raise ``NotAuthenticated``."""
    user = request.user
    if not isinstance(user, User) or not user.is_authenticated:
        raise NotAuthenticated()
    return user


class OwnedModelViewSet(viewsets.ModelViewSet[Any]):
    """ModelViewSet for ``OwnedModel`` subclasses, scoped to the requesting user.

    * Objects of other users do not exist as far as the API is concerned: 404, not 403.
    * The owner is taken from the session on create and can never be changed afterwards,
      even if a serializer exposes an ``owner`` field.
    """

    permission_classes = [IsAuthenticated, IsOwner]

    def get_queryset(self) -> QuerySet[Any]:
        queryset = super().get_queryset()
        if not isinstance(queryset, OwnedQuerySet):
            raise ImproperlyConfigured(
                f"{type(self).__name__}.queryset must come from an OwnedModel manager, "
                f"got {type(queryset).__name__}."
            )
        return queryset.for_user(self.request.user)

    def perform_create(self, serializer: BaseSerializer[Any]) -> None:
        serializer.save(owner=self.request.user)

    def perform_update(self, serializer: BaseSerializer[Any]) -> None:
        # The queryset only contains the user's own objects, so this keeps the owner unchanged.
        serializer.save(owner=self.request.user)
