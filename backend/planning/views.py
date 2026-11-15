import re
from datetime import date
from typing import Any
from uuid import UUID

from django.db.models import Count
from rest_framework import serializers, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import BaseThrottle
from rest_framework.views import APIView

from accounts.models import User
from coach.providers.base import ProviderError
from coach.services import NotConfiguredError
from coach.views import provider_problem
from integrations import services as integrations
from integrations.intervals import IntervalsError
from integrations.intervals import InvalidKeyError as IntervalsKeyError

from . import services
from .generation import NoTimeAvailable, PlanNotUsable, WeekNotPlannable, generate, plannable_weeks
from .models import WeeklyPlan
from .push import NotConfirmed, PushResult, export_state, push
from .serializers import finding_data, plan_data, push_data, push_problem_data, summary_data
from .targets import Targets
from .throttles import PlanGenerateThrottle, PlanPushThrottle
from .validation import Report

# Fixed texts, with a code the client can act on: nothing the provider said and nothing of the
# coach's answer goes into an error.
NOT_CONFIGURED = "No AI provider is set up."
NOT_PLANNABLE = "This week cannot be planned."
NO_TIME = "You have no training time for this week. Enter it on the Training time page."
NOT_FOUND = "There is no such plan."
NOT_A_DRAFT = "Only a draft can be confirmed or discarded."
NOT_CONFIRMABLE = "The plan has errors and cannot be confirmed."
NOT_USABLE = "The coach did not give a plan that can be used. Please try again."
# Why a plan could not be sent to Intervals.icu, by code. Nothing Intervals.icu said is in them.
PUSH_PROBLEMS = {
    "not_confirmed": "Only a confirmed plan can be sent to Intervals.icu.",
    "not_connected": "Intervals.icu is not connected. Connect it on the Connections page.",
    "invalid_key": "Intervals.icu did not accept the stored API key. Connect it again.",
    "unexpected": "Intervals.icu answered in an unexpected way. Please try again later.",
}

_WEEK = re.compile(r"\d{4}-\d{2}-\d{2}")


def _user(request: Request) -> User:
    assert isinstance(request.user, User)  # IsAuthenticated is the default permission
    return request.user


def _error(http_status: int, code: str, detail: str, **extra: Any) -> Response:
    return Response({"detail": detail, "code": code, **extra}, status=http_status)


def _detail(
    user: User,
    plan: WeeklyPlan,
    report: Report | None = None,
    sent: dict[str, Any] | None = None,
) -> Response:
    """The plan as the API shows it. A draft comes with a report (the one given, else a fresh
    one); a plan that was decided on does not: the checks are about what can still be done. A
    confirmed plan comes with what is known about its events in Intervals.icu, and ``sent`` is the
    result of a push that was just made."""
    week_plan = services.load(user, plan.pk)
    if plan.status != WeeklyPlan.Status.DRAFT:
        report = None
    elif report is None:
        report = services.validate(user, plan.pk)
    export = export_state(user, plan) if plan.status == WeeklyPlan.Status.CONFIRMED else None
    data = plan_data(plan, week_plan, report, Targets(user), export)
    if sent is not None:
        data["push"] = sent
    return Response(data)


def _push_problem(error: Exception) -> str:
    """The code for what stopped a push before it began."""
    if isinstance(error, NotConfirmed):
        return "not_confirmed"
    if isinstance(error, integrations.NotConnectedError):
        return "not_connected"
    if isinstance(error, IntervalsKeyError):
        return "invalid_key"
    return "unexpected"


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
        except NoTimeAvailable:
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


class PlanView(APIView):
    http_method_names = ["get", "head", "options"]

    def get(self, request: Request, plan_id: UUID) -> Response:
        user = _user(request)
        try:
            return _detail(user, services.get(user, plan_id))
        except services.PlanNotFound:
            return _error(status.HTTP_404_NOT_FOUND, "not_found", NOT_FOUND)


class ConfirmBody(serializers.Serializer[Any]):
    # Send the week to Intervals.icu right after confirming it (never without being asked).
    push = serializers.BooleanField(required=False, default=False)


class ConfirmView(APIView):
    throttle_classes = [PlanPushThrottle]
    http_method_names = ["post", "options"]

    def get_throttles(self) -> list[BaseThrottle]:
        # Only confirming *and sending* makes the server call Intervals.icu.
        wants_push = isinstance(self.request.data, dict) and self.request.data.get("push") is True
        return super().get_throttles() if wants_push else []

    def post(self, request: Request, plan_id: UUID) -> Response:
        user = _user(request)
        body = ConfirmBody(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            plan = services.confirm(user, plan_id)
            if not body.validated_data["push"]:
                return _detail(user, plan)
            # The week is confirmed whatever happens next: a problem with Intervals.icu is part of
            # the answer, not a failure of the confirmation.
            try:
                sent = push_data(push(user, plan_id))
            except (NotConfirmed, integrations.NotConnectedError, IntervalsError) as error:
                code = _push_problem(error)
                sent = push_problem_data(code, PUSH_PROBLEMS[code])
            return _detail(user, plan, sent=sent)
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


class PushView(APIView):
    """Sends a confirmed week to the user's own Intervals.icu calendar. Synchronous: one call per
    workout. What went wrong with single workouts is in the answer, per workout."""

    throttle_classes = [PlanPushThrottle]
    http_method_names = ["post", "options"]

    def post(self, request: Request, plan_id: UUID) -> Response:
        user = _user(request)
        try:
            result: PushResult = push(user, plan_id)
            return _detail(user, services.get(user, plan_id), sent=push_data(result))
        except services.PlanNotFound:
            return _error(status.HTTP_404_NOT_FOUND, "not_found", NOT_FOUND)
        except NotConfirmed:
            return _error(status.HTTP_409_CONFLICT, "not_confirmed", PUSH_PROBLEMS["not_confirmed"])
        except integrations.NotConnectedError:
            return _error(status.HTTP_409_CONFLICT, "not_connected", PUSH_PROBLEMS["not_connected"])
        except IntervalsKeyError:
            return _error(status.HTTP_502_BAD_GATEWAY, "invalid_key", PUSH_PROBLEMS["invalid_key"])
        except IntervalsError:
            return _error(status.HTTP_502_BAD_GATEWAY, "unexpected", PUSH_PROBLEMS["unexpected"])


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
