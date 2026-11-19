from typing import Any
from uuid import UUID

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from coach.providers.base import ProviderError
from coach.services import NotConfiguredError
from coach.views import provider_problem
from goals.services import today_of
from planning.serializers import finding_data
from planning.validation import Report

from . import services
from .done import done_week_totals
from .generation import (
    NothingToPlan,
    PlanNotChangeable,
    PlanNotUsable,
    PlanUnchanged,
    change,
    generate,
)
from .inputs import skeleton_for
from .load import planned_week_load
from .models import SeasonPlanVersion
from .reassessment import reassess
from .serializers import plan_detail, plan_summary
from .storage import skeleton_data
from .throttles import SeasonGenerateThrottle

# Fixed texts, with a code the client can act on: nothing the provider said and nothing of the
# coach's answer goes into an error.
NOT_CONFIGURED = "No AI provider is set up."
NO_TIME = (
    "You have no training time in the weeks of your season. Enter it on the Training time page."
)
NOT_FOUND = "There is no such season plan."
NOT_A_DRAFT = "Only a draft can be confirmed or discarded."
NOT_RESTORABLE = "Only a version that was replaced or discarded can be restored."
NOT_CHANGEABLE = (
    "Only the confirmed version and a draft can be changed. Restore an older version first."
)
UNCHANGED = "The coach gave the season back as it was. Say more clearly what you want changed."
NOT_CONFIRMABLE = "The plan has errors and cannot be confirmed."
NOT_USABLE = "The coach did not give a plan that can be used. Please try again."


def _user(request: Request) -> User:
    assert isinstance(request.user, User)  # IsAuthenticated is the default permission
    return request.user


def _error(http_status: int, code: str, detail: str, **extra: Any) -> Response:
    return Response({"detail": detail, "code": code, **extra}, status=http_status)


def _detail(user: User, plan: SeasonPlanVersion, report: Report | None = None) -> Response:
    """The plan as the API shows it. A draft comes with a report (the one given, else a fresh
    one); a plan that was decided on does not."""
    loaded = services.load(user, plan.pk)
    if plan.status != SeasonPlanVersion.Status.DRAFT:
        report = None
    elif report is None:
        report = services.validate(user, plan.pk)
    done = None
    if plan.status == SeasonPlanVersion.Status.CONFIRMED:
        # Done minutes and load for begun weeks, including the current week so far.
        today = today_of(user)
        begun = [
            week.week_start for week in loaded.context.skeleton.weeks if week.week_start <= today
        ]
        done = done_week_totals(user, begun)
    planned = planned_week_load(user, loaded.plan.weeks)
    return Response(plan_detail(plan, loaded, report, planned, done))


class SeasonView(APIView):
    """The skeleton of the signed-in user's season. It is worked out on every request from what
    the user has now and stored nowhere; there is no id and no user parameter."""

    http_method_names = ["get", "head", "options"]

    def get(self, request: Request) -> Response:
        return Response(skeleton_data(skeleton_for(_user(request))))


class ReassessmentView(APIView):
    """Changes from the signed-in user's confirmed season, without acknowledging them."""

    http_method_names = ["get", "head", "options"]

    def get(self, request: Request) -> Response:
        return Response(reassess(_user(request)))


class PlansView(APIView):
    """The versions of the season plan of the user, the newest first."""

    http_method_names = ["get", "head", "options"]

    def get(self, request: Request) -> Response:
        versions = services.list_versions(_user(request))
        return Response({"plans": [plan_summary(plan) for plan in versions]})


class GenerateView(APIView):
    """Asks the user's own coach to fill the season. Synchronous: the answer can take minutes."""

    throttle_classes = [SeasonGenerateThrottle]
    http_method_names = ["post", "options"]

    def post(self, request: Request) -> Response:
        user = _user(request)
        try:
            generated = generate(user)
        except NothingToPlan:
            return _error(status.HTTP_409_CONFLICT, "no_time", NO_TIME)
        except NotConfiguredError:
            return _error(status.HTTP_409_CONFLICT, "not_configured", NOT_CONFIGURED)
        except PlanNotUsable as error:
            return _error(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "not_usable",
                NOT_USABLE,
                problems=[{"path": p.path, "message": p.message} for p in error.problems],
            )
        except ProviderError as error:
            return provider_problem(error)
        response = _detail(user, generated.plan, generated.report)
        response.status_code = status.HTTP_201_CREATED
        return response


class _Text(serializers.CharField):
    """Text and nothing else: DRF would turn the number 5 into "5"."""

    def to_internal_value(self, data: Any) -> str:
        if not isinstance(data, str):
            self.fail("invalid")
        return super().to_internal_value(data)


class ChangeBody(serializers.Serializer[Any]):
    # The limits and the plain text are checked by the service; this only keeps absurd bodies out.
    request = _Text(max_length=4000, allow_blank=True, trim_whitespace=False)


class ChangeView(APIView):
    """Asks the user's own coach to change a version as the athlete wishes. Synchronous: the answer
    can take minutes. The answer is the new draft with its checks; the version in the address is
    not touched. Nothing of the request is repeated in an error but the fixed texts of its field."""

    throttle_classes = [SeasonGenerateThrottle]
    http_method_names = ["post", "options"]

    def post(self, request: Request, plan_id: UUID) -> Response:
        user = _user(request)
        body = ChangeBody(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            changed = change(user, plan_id, body.validated_data["request"])
        except DjangoValidationError as error:
            raise serializers.ValidationError(error.message_dict) from None
        except services.PlanNotFound:
            return _error(status.HTTP_404_NOT_FOUND, "not_found", NOT_FOUND)
        except PlanNotChangeable:
            return _error(status.HTTP_409_CONFLICT, "not_changeable", NOT_CHANGEABLE)
        except NothingToPlan:
            return _error(status.HTTP_409_CONFLICT, "no_time", NO_TIME)
        except NotConfiguredError:
            return _error(status.HTTP_409_CONFLICT, "not_configured", NOT_CONFIGURED)
        except PlanUnchanged:
            return _error(status.HTTP_422_UNPROCESSABLE_ENTITY, "unchanged", UNCHANGED)
        except PlanNotUsable as error:
            return _error(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "not_usable",
                NOT_USABLE,
                problems=[{"path": p.path, "message": p.message} for p in error.problems],
            )
        except ProviderError as error:
            return provider_problem(error)
        response = _detail(user, changed.plan, changed.report)
        response.status_code = status.HTTP_201_CREATED
        return response


class PlanView(APIView):
    http_method_names = ["get", "head", "options"]

    def get(self, request: Request, plan_id: UUID) -> Response:
        user = _user(request)
        try:
            return _detail(user, services.get(user, plan_id))
        except services.PlanNotFound:
            return _error(status.HTTP_404_NOT_FOUND, "not_found", NOT_FOUND)


class ConfirmView(APIView):
    http_method_names = ["post", "options"]

    def post(self, request: Request, plan_id: UUID) -> Response:
        user = _user(request)
        try:
            return _detail(user, services.confirm(user, plan_id))
        except services.PlanNotFound:
            return _error(status.HTTP_404_NOT_FOUND, "not_found", NOT_FOUND)
        except services.PlanStateError:
            return _error(status.HTTP_409_CONFLICT, "not_a_draft", NOT_A_DRAFT)
        except services.PlanNotConfirmable as error:
            return _error(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "not_confirmable",
                NOT_CONFIRMABLE,
                findings=[finding_data(finding) for finding in error.report.findings],
            )


class RestoreView(APIView):
    """Brings back a version that was replaced or discarded, as a new draft (the version in the
    address is not touched). The answer is the new draft with its checks."""

    http_method_names = ["post", "options"]

    def post(self, request: Request, plan_id: UUID) -> Response:
        user = _user(request)
        try:
            plan = services.restore(user, plan_id)
        except services.PlanNotFound:
            return _error(status.HTTP_404_NOT_FOUND, "not_found", NOT_FOUND)
        except services.PlanNotRestorable:
            return _error(status.HTTP_409_CONFLICT, "not_restorable", NOT_RESTORABLE)
        response = _detail(user, plan)
        response.status_code = status.HTTP_201_CREATED
        return response


class DiscardView(APIView):
    http_method_names = ["post", "options"]

    def post(self, request: Request, plan_id: UUID) -> Response:
        user = _user(request)
        try:
            return _detail(user, services.discard(user, plan_id))
        except services.PlanNotFound:
            return _error(status.HTTP_404_NOT_FOUND, "not_found", NOT_FOUND)
        except services.PlanStateError:
            return _error(status.HTTP_409_CONFLICT, "not_a_draft", NOT_A_DRAFT)
