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
from .models import RULES, AthleteProfile, BestTime
from .serializers import AthleteInput, BestTimeInput, ThresholdInput, athlete_data
from .sync import sync_from_intervals
from .vdot import DISTANCES

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
        """Changes the fields that are sent; ``null`` clears one. Nothing is saved unless every
        field is usable."""
        user = _user(request)
        serializer = AthleteInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        profile = AthleteProfile.objects.for_user(user).first() or AthleteProfile(owner=user)
        changed = _apply(profile, serializer.validated_data)
        try:
            profile.clean()
        except DjangoValidationError as error:
            raise serializers.ValidationError(_athlete_messages(error)) from None
        if profile.pk is None:
            profile.save()
        else:
            profile.save(update_fields=changed)
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


class BestTimeView(APIView):
    """The best time of the user over one distance; a new one replaces the old one."""

    def put(self, request: Request, distance: str) -> Response:
        _require_distance(distance)
        serializer = BestTimeInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = _user(request)
        candidate = BestTime(owner=user, distance=distance, **serializer.validated_data)
        try:
            candidate.clean()
        except DjangoValidationError as error:
            raise serializers.ValidationError(_messages(error)) from None
        BestTime.objects.update_or_create(
            owner=user,
            distance=distance,
            defaults={"seconds": candidate.seconds, "date": candidate.date},
        )
        return _answer(user)

    def delete(self, request: Request, distance: str) -> Response:
        """Removes the time. Removing one that is not there is fine."""
        _require_distance(distance)
        user = _user(request)
        BestTime.objects.for_user(user).filter(distance=distance).delete()
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


def _apply(profile: AthleteProfile, changes: dict[str, Any]) -> list[str]:
    """Puts the changes on the profile (not saved) and names the columns that were touched. What
    is not said is an empty text or list in the database and ``None`` in a number."""
    touched: list[str] = []

    def put(column: str, value: Any) -> None:
        setattr(profile, column, value)
        touched.append(column)

    for name, value in changes.items():
        if name == "training_years":
            for sport, years in value.items():
                put(f"years_{sport}", years)
        elif name in ("sex", "strength_experience"):
            put(name, value or "")
        else:
            put(name, value)
    return touched


def _athlete_messages(error: DjangoValidationError) -> dict[str, Any]:
    """The messages by field of the API: the years of every sport are one field there."""
    messages: dict[str, list[str]] = {}
    for column, texts in error.message_dict.items():
        name = "training_years" if column.startswith("years_") else column
        messages.setdefault(name, []).extend(texts)
    return messages


def _require_distance(distance: str) -> None:
    if distance not in DISTANCES:
        raise Http404


def _require_known(sport: str, metric: str) -> None:
    if (sport, metric) not in RULES:
        raise Http404


def _messages(error: DjangoValidationError) -> dict[str, Any]:
    return error.message_dict
