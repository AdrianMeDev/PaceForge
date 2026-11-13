from django.db import transaction
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User

from .models import AvailabilitySettings, WeekdayMinutes
from .serializers import AvailabilityInput, availability_data


def _user(request: Request) -> User:
    assert isinstance(request.user, User)  # IsAuthenticated is the default permission
    return request.user


def _answer(user: User) -> Response:
    settings = AvailabilitySettings.objects.for_user(user).first()
    weekdays = list(WeekdayMinutes.objects.for_user(user))
    return Response(availability_data(settings, weekdays))


class AvailabilityView(APIView):
    """The signed-in user's own training time; there is no id and no user parameter."""

    http_method_names = ["get", "patch", "head", "options"]

    def get(self, request: Request) -> Response:
        # Reading writes nothing: rows are created when the user first saves something.
        return _answer(_user(request))

    def patch(self, request: Request) -> Response:
        user = _user(request)
        serializer = AvailabilityInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        with transaction.atomic():
            if "weekdays" in data:
                WeekdayMinutes.objects.bulk_create(
                    [
                        WeekdayMinutes(owner=user, weekday=weekday, minutes=minutes)
                        for weekday, minutes in enumerate(data["weekdays"])
                    ],
                    update_conflicts=True,
                    unique_fields=["owner", "weekday"],
                    update_fields=["minutes"],
                )
            settings_fields = [
                name for name in ("weekly_budget_minutes", "limitations") if name in data
            ]
            if settings_fields:
                settings, _ = AvailabilitySettings.objects.get_or_create(owner=user)
                for name in settings_fields:
                    setattr(settings, name, data[name])
                settings.save(update_fields=settings_fields)
        return _answer(user)
