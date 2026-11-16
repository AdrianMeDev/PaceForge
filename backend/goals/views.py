from typing import Any

from django.db import IntegrityError, transaction
from django.db.models import Case, F, IntegerField, QuerySet, Value, When
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer, ValidationError

from accounts.models import User
from core.views import OwnedModelViewSet

from .assessing import assess_goals
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
                    When(priority=Goal.Priority.SECONDARY, then=Value(1)),
                    default=Value(2),
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
        # The judgements of the goals, by id; the list fills it with one set of queries.
        context["assessments"] = {}
        return context

    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        user = request.user
        assert isinstance(user, User)
        goals = list(self.filter_queryset(self.get_queryset()))
        serializer = self.get_serializer(goals, many=True)
        context = serializer.context
        # a general goal has nothing to judge and is not asked about
        judged = [goal for goal in goals if goal.kind != Goal.Kind.GENERAL]
        context["assessments"].update(assess_goals(user, judged, context["today"]))
        return Response(serializer.data)

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
