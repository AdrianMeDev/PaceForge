from http import HTTPStatus
from typing import Any

from django.conf import settings
from django.db.models import QuerySet
from rest_framework.parsers import MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer
from rest_framework.views import APIView

from accounts.models import User
from core.views import OwnedModelViewSet

from . import services
from .models import Activity
from .pagination import ActivityPagination
from .parsing import ActivityFileError
from .serializers import ActivityDetailSerializer, ActivitySerializer
from .throttles import ActivityImportThrottle

NO_FILE = "No file was uploaded."
EMPTY_FILE = "The file is empty."
TOO_LARGE = "The file is too large."
DUPLICATE = "This activity has already been imported."


def _user(request: Request) -> User:
    assert isinstance(request.user, User)  # IsAuthenticated is the default permission
    return request.user


def _refused(message: str, status: HTTPStatus, **extra: Any) -> Response:
    """Nothing from the file goes into an answer; the texts are fixed."""
    return Response({"detail": message, **extra}, status=status)


class ActivityViewSet(OwnedModelViewSet):
    """The signed-in user's own activities: list, detail and delete. Activities are created
    only by importing a file, and are never edited."""

    queryset = Activity.objects.order_by("-start_time", "-id")
    http_method_names = ["get", "delete", "head", "options"]
    pagination_class = ActivityPagination
    # An id that is no UUID is a 404 without reaching the database.
    lookup_value_regex = "[0-9a-fA-F-]{32,36}"

    def get_queryset(self) -> QuerySet[Any]:
        queryset = super().get_queryset()
        # The laps are only needed for one activity.
        return queryset.defer("laps") if self.action == "list" else queryset

    def get_serializer_class(self) -> type[BaseSerializer[Any]]:
        return ActivitySerializer if self.action == "list" else ActivityDetailSerializer


class ActivityImportView(APIView):
    parser_classes = [MultiPartParser]
    throttle_classes = [ActivityImportThrottle]

    def post(self, request: Request) -> Response:
        upload = request.FILES.get("file")
        if upload is None:
            return _refused(NO_FILE, HTTPStatus.BAD_REQUEST)
        if upload.size == 0:
            return _refused(EMPTY_FILE, HTTPStatus.BAD_REQUEST)
        if upload.size > settings.ACTIVITY_UPLOAD_MAX_BYTES:
            return _refused(TOO_LARGE, HTTPStatus.REQUEST_ENTITY_TOO_LARGE)

        try:
            activity = services.import_activity(_user(request), upload.read())
        except services.FileTooLargeError:
            return _refused(TOO_LARGE, HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
        except services.DuplicateActivityError as duplicate:
            return _refused(DUPLICATE, HTTPStatus.CONFLICT, existing_id=str(duplicate.existing_id))
        except ActivityFileError as error:
            return _refused(str(error), HTTPStatus.BAD_REQUEST)
        return Response(ActivitySerializer(activity).data, status=HTTPStatus.CREATED)
