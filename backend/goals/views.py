from typing import Any

from django.db import IntegrityError, transaction
from django.db.models import Case, F, IntegerField, QuerySet, Value, When
from rest_framework.serializers import BaseSerializer, ValidationError

from accounts.models import User
from core.views import OwnedModelViewSet

from .models import Goal
from .serializers import MAIN_TAKEN, GoalSerializer
from .services import today_of

_MAIN_GOAL_CONSTRAINT = "goals_one_active_main_goal"


class GoalViewSet(OwnedModelViewSet):
    """The signed-in user's own goals: list, create, read, change some fields, delete."""

    queryset = Goal.objects.all()
    serializer_class = GoalSerializer
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    pagination_class = None
    # An id that is no UUID is a 404 without reaching the database.
    lookup_value_regex = "[0-9a-fA-F-]{32,36}"

    def get_queryset(self) -> QuerySet[Any]:
        return (
            super()
            .get_queryset()
            .annotate(
                status_rank=Case(
                    When(status=Goal.Status.ACTIVE, then=Value(0)),
                    When(status=Goal.Status.ACHIEVED, then=Value(1)),
                    default=Value(2),
                    output_field=IntegerField(),
                ),
                priority_rank=Case(
                    When(priority=Goal.Priority.MAIN, then=Value(0)),
                    default=Value(1),
                    output_field=IntegerField(),
                ),
            )
            .order_by(
                "status_rank",
                "priority_rank",
                F("target_date").asc(nulls_last=True),
                "created_at",
                "id",
            )
        )

    def get_serializer_context(self) -> dict[str, Any]:
        context = dict(super().get_serializer_context())
        user = self.request.user
        assert isinstance(user, User)  # IsAuthenticated is the default permission
        # One lookup of the time zone per request, not one per goal.
        context["today"] = today_of(user)
        return context

    def perform_create(self, serializer: BaseSerializer[Any]) -> None:
        self._save(super().perform_create, serializer)

    def perform_update(self, serializer: BaseSerializer[Any]) -> None:
        self._save(super().perform_update, serializer)

    @staticmethod
    def _save(save: Any, serializer: BaseSerializer[Any]) -> None:
        """Two requests that both pass the check for the main goal meet at the database."""
        try:
            with transaction.atomic():
                save(serializer)
        except IntegrityError as error:
            if _MAIN_GOAL_CONSTRAINT not in str(error):
                raise
            raise ValidationError({"priority": [MAIN_TAKEN]}) from None
