from typing import Any

from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView


class IsOwner(BasePermission):
    """Object-level check that the requesting user owns the object.

    This is the second line of defence: ``OwnedModelViewSet`` already hides foreign objects
    (404) by filtering the queryset.
    """

    def has_object_permission(self, request: Request, view: APIView, obj: Any) -> bool:
        return bool(request.user.is_authenticated and obj.owner_id == request.user.pk)
