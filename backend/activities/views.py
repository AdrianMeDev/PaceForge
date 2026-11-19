from dataclasses import asdict
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
from athletes.estimates import refresh_estimates_safely
from athletes.views import KEY_NOT_ACCEPTED
from core.views import OwnedModelViewSet
from integrations import services as integrations
from integrations.intervals import IntervalsError, InvalidKeyError
from integrations.throttles import ProviderConnectionThrottle
from integrations.views import failure_response

from . import services
from .models import Activity
from .pagination import ActivityPagination
from .parsing import ActivityFileError
from .serializers import (
    ActivityDetailSerializer,
    ActivityRatingSerializer,
    ActivitySerializer,
    ManualActivitySerializer,
)
from .sync import sync_from_intervals
from .throttles import ActivityImportThrottle

NO_FILE = "No file was uploaded."
EMPTY_FILE = "The file is empty."
TOO_LARGE = "The file is too large."
DUPLICATE = "This activity has already been imported."
UNKNOWN_SPORT = "Unknown sport."


def _user(request: Request) -> User:
    assert isinstance(request.user, User)  # IsAuthenticated is the default permission
    return request.user


def _refused(message: str, status: HTTPStatus, **extra: Any) -> Response:
    """Nothing from the file goes into an answer; the texts are fixed."""
    return Response({"detail": message, **extra}, status=status)


class ActivityViewSet(OwnedModelViewSet):
    """The signed-in user's own activities: list, detail, delete and rate. Activities are created
    only by importing a file or entering one by hand, and what they record is never edited: after
    the fact the user can only say how hard it felt (``rpe``) and add a note."""

    queryset = Activity.objects.order_by("-start_time", "-id")
    http_method_names = ["get", "patch", "delete", "head", "options"]
    pagination_class = ActivityPagination
    # An id that is no UUID is a 404 without reaching the database.
    lookup_value_regex = "[0-9a-fA-F-]{32,36}"

    def get_queryset(self) -> QuerySet[Any]:
        queryset = super().get_queryset()
        if self.action != "list":
            return queryset
        sport = self.request.query_params.get("sport")
        if sport is not None:
            queryset = queryset.filter(sport=sport)
        # The laps are only needed for one activity.
        return queryset.defer("laps")

    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """The list, newest first; ``?sport=`` keeps one sport (count and pages follow)."""
        sport = request.query_params.get("sport")
        if sport is not None and sport not in Activity.Sport.values:
            # The value is not repeated: it is the caller's text.
            return _refused(UNKNOWN_SPORT, HTTPStatus.BAD_REQUEST)
        return super().list(request, *args, **kwargs)

    def partial_update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        activity = self.get_object()
        serializer = ActivityRatingSerializer(activity, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(ActivityDetailSerializer(activity).data)

    def perform_destroy(self, instance: Activity) -> None:
        instance.delete()
        refresh_estimates_safely(_user(self.request))

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
        refresh_estimates_safely(_user(request))
        return Response(ActivitySerializer(activity).data, status=HTTPStatus.CREATED)


class ManualActivityView(APIView):
    """Enter a session by hand: for what no watch recorded, such as strength training, and for the
    sessions that only Strava has. It counts like an imported activity."""

    throttle_classes = [ActivityImportThrottle]
    http_method_names = ["post", "options"]

    def post(self, request: Request) -> Response:
        user = _user(request)
        serializer = ManualActivitySerializer(data=request.data, context={"user": user})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            activity = services.enter_activity(
                user,
                sport=data["sport"],
                start=data["start"],
                duration_minutes=data["duration_minutes"],
                distance_km=data.get("distance_km"),
                rpe=data.get("rpe"),
                notes=data.get("notes", ""),
            )
        except services.DuplicateActivityError as duplicate:
            return _refused(DUPLICATE, HTTPStatus.CONFLICT, existing_id=str(duplicate.existing_id))
        return Response(ActivitySerializer(activity).data, status=HTTPStatus.CREATED)


class ActivitySyncView(APIView):
    """Import the recent activities from the user's own Intervals.icu connection."""

    # The same counter as connecting and checking: all of them make the server call Intervals.icu.
    throttle_classes = [ProviderConnectionThrottle]
    http_method_names = ["post", "options"]

    def post(self, request: Request) -> Response:
        user = _user(request)
        try:
            counts = sync_from_intervals(user)
        except integrations.NotConnectedError:
            return _refused("Not connected.", HTTPStatus.NOT_FOUND)
        except InvalidKeyError:
            return _refused(KEY_NOT_ACCEPTED, HTTPStatus.CONFLICT)
        except IntervalsError as error:
            return failure_response(error)
        connection = integrations.get_connection(user)
        last_sync_at = connection.last_sync_at if connection is not None else None
        return Response({**asdict(counts), "last_sync_at": last_sync_at})
