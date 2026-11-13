from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from rest_framework import serializers, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from integrations.intervals import IntervalsError, InvalidKeyError
from integrations.services import NotConnectedError
from integrations.throttles import ProviderConnectionThrottle
from integrations.views import failure_response

from . import thresholds
from .models import RULES, AthleteProfile
from .serializers import ThresholdInput, TimezoneInput, athlete_data
from .sync import sync_from_intervals

KEY_NOT_ACCEPTED = (
    "Intervals.icu did not accept the stored API key. Enter it again on the Connections page."
)


def _user(request: Request) -> User:
    assert isinstance(request.user, User)  # IsAuthenticated is the default permission
    return request.user


def _answer(user: User) -> Response:
    profile = AthleteProfile.objects.for_user(user).first()
    return Response(athlete_data(user, profile))


class AthleteView(APIView):
    """The signed-in user's own athlete profile; there is no id and no user parameter."""

    def get(self, request: Request) -> Response:
        # Reading writes nothing: the profile row is created when the user first changes it.
        return _answer(_user(request))

    def patch(self, request: Request) -> Response:
        user = _user(request)
        serializer = TimezoneInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        profile, _ = AthleteProfile.objects.get_or_create(owner=user)
        profile.timezone = serializer.validated_data["timezone"]
        profile.save(update_fields=["timezone"])
        return _answer(user)


class ThresholdView(APIView):
    """The value the user typed in for one threshold; other sources are not touched."""

    def put(self, request: Request, sport: str, metric: str) -> Response:
        _require_known(sport, metric)
        serializer = ThresholdInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = _user(request)
        try:
            thresholds.set_manual(user, sport, metric, serializer.validated_data["value"])
        except DjangoValidationError as error:
            raise serializers.ValidationError(_messages(error)) from None
        return _answer(user)

    def delete(self, request: Request, sport: str, metric: str) -> Response:
        """Back to automatic. Clearing a value that is not there is fine."""
        _require_known(sport, metric)
        user = _user(request)
        thresholds.clear_manual(user, sport, metric)
        return _answer(user)


class SyncView(APIView):
    """Read the thresholds from the user's own Intervals.icu connection."""

    # The same counter as connecting and checking: all of them make the server call Intervals.icu.
    throttle_classes = [ProviderConnectionThrottle]

    def post(self, request: Request) -> Response:
        user = _user(request)
        try:
            sync_from_intervals(user)
        except NotConnectedError:
            return Response({"detail": "Not connected."}, status=status.HTTP_404_NOT_FOUND)
        except InvalidKeyError:
            return Response({"detail": KEY_NOT_ACCEPTED}, status=status.HTTP_409_CONFLICT)
        except IntervalsError as error:
            return failure_response(error)
        return _answer(user)


def _require_known(sport: str, metric: str) -> None:
    if (sport, metric) not in RULES:
        raise Http404


def _messages(error: DjangoValidationError) -> dict[str, Any]:
    return error.message_dict
