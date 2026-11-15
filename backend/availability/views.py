from datetime import date
from functools import cached_property
from typing import Any

from django.db import transaction
from django.db.models import Case, DateField, F, IntegerField, QuerySet, Value, When
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from core.views import OwnedModelViewSet
from goals.services import today_of

from .intensity import LIMIT_NAMES
from .models import AvailabilitySettings, Limitation, UnavailablePeriod, WeekdayMinutes
from .serializers import (
    AvailabilityInput,
    LimitationSerializer,
    PeriodSerializer,
    availability_data,
)


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
        stored = AvailabilitySettings.objects.for_user(user).first()
        serializer = AvailabilityInput(data=request.data, context={"settings": stored})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        with transaction.atomic():
            # What was sent decides what is written; a row that is created for the first time has
            # the defaults for the rest (no time, two sessions, every part of the day).
            day_fields = {
                field: sent
                for field, sent in (
                    ("minutes", data.get("weekdays")),
                    ("double_allowed", data.get("double_days")),
                    ("slots", data.get("time_windows")),
                )
                if sent is not None
            }
            if day_fields:
                WeekdayMinutes.objects.bulk_create(
                    [
                        WeekdayMinutes(
                            owner=user,
                            weekday=weekday,
                            **{field: sent[weekday] for field, sent in day_fields.items()},
                        )
                        for weekday in range(7)
                    ],
                    update_conflicts=True,
                    unique_fields=["owner", "weekday"],
                    update_fields=list(day_fields),
                )
            settings_fields = [
                name
                for name in (
                    "weekly_budget_minutes",
                    "typical_weekly_minutes",
                    "sports",
                    "stretching",
                    "limitations",
                    "intensity_level",
                    *LIMIT_NAMES,
                )
                if name in data
            ]
            if settings_fields:
                settings, _ = AvailabilitySettings.objects.get_or_create(owner=user)
                for name in settings_fields:
                    setattr(settings, name, data[name])
                settings.save(update_fields=settings_fields)
        return _answer(user)


class PeriodViewSet(OwnedModelViewSet):
    """The signed-in user's own periods of absence: list, create, read, change, delete."""

    queryset = UnavailablePeriod.objects.all()
    serializer_class = PeriodSerializer
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    pagination_class = None
    # An id that is no UUID is a 404 without reaching the database.
    lookup_value_regex = "[0-9a-fA-F-]{32,36}"

    @cached_property
    def today(self) -> date:
        return today_of(_user(self.request))

    def get_queryset(self) -> QuerySet[Any]:
        """Periods that are going on or still to come first, the nearest first; then the past
        ones, the latest first."""
        coming = When(end_date__gte=self.today, then=Value(0))
        return (
            super()
            .get_queryset()
            .annotate(rank=Case(coming, default=Value(1), output_field=IntegerField()))
            .order_by(
                "rank",
                Case(When(rank=0, then=F("start_date")), output_field=DateField()).asc(
                    nulls_last=True
                ),
                Case(When(rank=1, then=F("end_date")), output_field=DateField()).desc(
                    nulls_last=True
                ),
                "id",
            )
        )

    def get_serializer_context(self) -> dict[str, Any]:
        context = dict(super().get_serializer_context())
        # One lookup of the time zone per request, not one per period.
        context["today"] = self.today
        return context


class LimitationViewSet(OwnedModelViewSet):
    """The signed-in user's own limitations: list, create, read, change, delete."""

    queryset = Limitation.objects.all()
    serializer_class = LimitationSerializer
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    pagination_class = None
    # An id that is no UUID is a 404 without reaching the database.
    lookup_value_regex = "[0-9a-fA-F-]{32,36}"

    def get_queryset(self) -> QuerySet[Any]:
        """Current entries first, then healed ones; the newest first within each (the ids are
        time-ordered)."""
        current = When(status="current", then=Value(0))
        return (
            super()
            .get_queryset()
            .annotate(rank=Case(current, default=Value(1), output_field=IntegerField()))
            .order_by("rank", "-id")
        )
