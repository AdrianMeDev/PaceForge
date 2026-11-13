from rest_framework import serializers, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import BaseThrottle
from rest_framework.views import APIView

from accounts.models import User
from integrations import services
from integrations.intervals import (
    IntervalsError,
    IntervalsUnavailableError,
    InvalidKeyError,
)
from integrations.models import ProviderConnection
from integrations.serializers import ConnectionSerializer, ConnectSerializer
from integrations.throttles import ProviderConnectionThrottle

UNAVAILABLE = "Intervals.icu cannot be reached right now. Please try again later."
UNEXPECTED = "Intervals.icu answered in an unexpected way. Please try again later."
KEY_REFUSED = "Intervals.icu did not accept this API key. Check that you copied all of it."


def _user(request: Request) -> User:
    assert isinstance(request.user, User)  # IsAuthenticated is the default permission
    return request.user


def _state(connection: ProviderConnection | None) -> Response:
    if connection is None:
        return Response({"connected": False})
    return Response(ConnectionSerializer(connection).data)


def failure_response(error: IntervalsError) -> Response:
    """Nothing about the request goes into the answer, least of all the key."""
    if isinstance(error, IntervalsUnavailableError):
        return Response({"detail": UNAVAILABLE}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    return Response({"detail": UNEXPECTED}, status=status.HTTP_502_BAD_GATEWAY)


class IntervalsConnectionView(APIView):
    """The signed-in user's own Intervals.icu connection; there is no id and no user parameter."""

    throttle_classes = [ProviderConnectionThrottle]

    def get_throttles(self) -> list[BaseThrottle]:
        # Only saving a key makes the server call Intervals.icu; reading and removing are free.
        return super().get_throttles() if self.request.method == "PUT" else []

    def get(self, request: Request) -> Response:
        return _state(services.get_connection(_user(request)))

    def put(self, request: Request) -> Response:
        serializer = ConnectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            connection = services.connect(_user(request), serializer.validated_data["api_key"])
        except InvalidKeyError:
            raise serializers.ValidationError({"api_key": [KEY_REFUSED]}) from None
        except IntervalsError as error:
            return failure_response(error)
        return _state(connection)

    def delete(self, request: Request) -> Response:
        services.disconnect(_user(request))
        return Response(status=status.HTTP_204_NO_CONTENT)


class IntervalsCheckView(APIView):
    throttle_classes = [ProviderConnectionThrottle]

    def post(self, request: Request) -> Response:
        try:
            connection = services.check(_user(request))
        except services.NotConnectedError:
            return Response({"detail": "Not connected."}, status=status.HTTP_404_NOT_FOUND)
        except IntervalsError as error:
            return failure_response(error)
        return _state(connection)
