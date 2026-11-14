import re
from datetime import date
from typing import Any
from uuid import UUID

from django.db.models import Count
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from coach.providers.base import (
    EndpointNotAllowedError,
    InvalidKeyError,
    ProviderError,
    ProviderUnavailableError,
    RateLimitedError,
)
from coach.services import NotConfiguredError
from coach.views import PROBLEMS

from . import services
from .generation import PlanNotUsable, WeekNotPlannable, generate, plannable_weeks
from .models import WeeklyPlan
from .serializers import finding_data, plan_data, summary_data
from .throttles import PlanGenerateThrottle
from .validation import Report

# Fixed texts, with a code the client can act on: nothing the provider said and nothing of the
# coach's answer goes into an error.
NOT_CONFIGURED = "No AI provider is set up."
NOT_PLANNABLE = "This week cannot be planned."
NOT_FOUND = "There is no such plan."
NOT_A_DRAFT = "Only a draft can be confirmed or discarded."
NOT_CONFIRMABLE = "The plan has errors and cannot be confirmed."
NOT_USABLE = "The coach did not give a plan that can be used. Please try again."

_WEEK = re.compile(r"\d{4}-\d{2}-\d{2}")


def _user(request: Request) -> User:
    assert isinstance(request.user, User)  # IsAuthenticated is the default permission
    return request.user


def _error(http_status: int, code: str, detail: str, **extra: Any) -> Response:
    return Response({"detail": detail, "code": code, **extra}, status=http_status)


def _detail(user: User, plan: WeeklyPlan, report: Report | None = None) -> Response:
    """The plan as the API shows it. A draft comes with a report (the one given, else a fresh
    one); a plan that was decided on does not: the checks are about what can still be done."""
    week_plan = services.load(user, plan.pk)
    if plan.status != WeeklyPlan.Status.DRAFT:
        report = None
    elif report is None:
        report = services.validate(user, plan.pk)
    return Response(plan_data(plan, week_plan, report))


class WeeksView(APIView):
    """The weeks that can be planned, each with the versions that exist of it."""

    http_method_names = ["get", "head", "options"]

    def get(self, request: Request) -> Response:
        user = _user(request)
        weeks = plannable_weeks(user)
        versions = (
            WeeklyPlan.objects.for_user(user)
            .filter(week_start__in=weeks)
            .annotate(workout_count=Count("workouts"))
            .order_by("week_start", "-version")
        )
        by_week: dict[date, list[dict[str, Any]]] = {week: [] for week in weeks}
        for plan in versions:
            by_week[plan.week_start].append(summary_data(plan, plan.workout_count))
        return Response(
            {"weeks": [{"week_start": week.isoformat(), "plans": by_week[week]} for week in weeks]}
        )


class GenerateView(APIView):
    """Asks the user's own coach for a draft of a week. Synchronous: the answer can take up to
    a minute or two."""

    throttle_classes = [PlanGenerateThrottle]
    http_method_names = ["post", "options"]

    def post(self, request: Request, week: str) -> Response:
        user = _user(request)
        try:
            monday = date.fromisoformat(week) if _WEEK.fullmatch(week) else None
        except ValueError:
            monday = None
        if monday is None:
            return _error(status.HTTP_404_NOT_FOUND, "week_not_plannable", NOT_PLANNABLE)
        try:
            generated = generate(user, monday)
        except WeekNotPlannable:
            return _error(status.HTTP_404_NOT_FOUND, "week_not_plannable", NOT_PLANNABLE)
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
            return _provider_problem(error)
        response = _detail(user, generated.plan, generated.report)
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


def _provider_problem(error: ProviderError) -> Response:
    if isinstance(error, InvalidKeyError):
        return _error(status.HTTP_502_BAD_GATEWAY, "invalid_key", PROBLEMS["invalid_key"])
    if isinstance(error, RateLimitedError):
        response = _error(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "rate_limited",
            PROBLEMS["rate_limited"],
            retry_after=error.retry_after,
        )
        if error.retry_after is not None:
            response["Retry-After"] = str(error.retry_after)
        return response
    if isinstance(error, ProviderUnavailableError):
        return _error(status.HTTP_503_SERVICE_UNAVAILABLE, "unavailable", PROBLEMS["unavailable"])
    if isinstance(error, EndpointNotAllowedError):
        return _error(status.HTTP_502_BAD_GATEWAY, "not_allowed", PROBLEMS["not_allowed"])
    return _error(status.HTTP_502_BAD_GATEWAY, "unexpected", PROBLEMS["unexpected"])
