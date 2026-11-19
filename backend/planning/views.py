import re
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from uuid import UUID

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count
from rest_framework import serializers, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import BaseThrottle
from rest_framework.views import APIView

from accounts.models import User
from activities.models import Activity
from coach.providers.base import ProviderError
from coach.services import NotConfiguredError
from coach.views import provider_problem
from goals.services import time_zone_of
from integrations import services as integrations
from integrations.intervals import IntervalsError
from integrations.intervals import InvalidKeyError as IntervalsKeyError
from season.weeks import confirmed_weeks

from . import services
from .briefing import season_week_data
from .editing import PlanNotRestorable, PlanNotRevisable, check, restore, revise
from .generation import NoTimeAvailable, PlanNotUsable, WeekNotPlannable, generate, plannable_weeks
from .load import week_load
from .models import WeeklyPlan
from .push import NotConfirmed, PushResult, export_state, push
from .schema import PlanFormatError
from .serializers import (
    finding_data,
    plan_data,
    push_data,
    push_problem_data,
    report_data,
    summary_data,
)
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
INVALID_PLAN = "The plan cannot be read. Please check the problems."
NOT_REVISABLE = "Only a draft or a confirmed plan can be changed. Restore an older version first."
NOT_RESTORABLE = "Only a version that was replaced or discarded can be restored."
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


def _monday(week: str) -> date | None:
    """The date in ``week`` if it is written ``YYYY-MM-DD`` and is a real day, else ``None``."""
    if not _WEEK.fullmatch(week):
        return None
    try:
        return date.fromisoformat(week)
    except ValueError:
        return None


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
    zone = time_zone_of(user)
    since = datetime.combine(plan.week_start, time.min, tzinfo=zone).astimezone(UTC)
    until = datetime.combine(plan.week_start + timedelta(days=7), time.min, tzinfo=zone).astimezone(
        UTC
    )
    activities = (
        Activity.objects.for_user(user)
        .filter(start_time__gte=since, start_time__lt=until)
        .only("sport", "training_load", "timer_seconds", "elapsed_seconds", "rpe")
    )
    data = plan_data(
        plan, week_plan, report, Targets(user), week_load(week_plan, activities), export
    )
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
    """The weeks that can be planned, each with the week of the confirmed season plan (``season``,
    ``null`` if there is none) and the versions that exist of it."""

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
        seasons = confirmed_weeks(user, weeks)
        return Response(
            {
                "weeks": [
                    {
                        "week_start": week.isoformat(),
                        "season": season_week_data(seasons.get(week)),
                        "plans": by_week[week],
                    }
                    for week in weeks
                ]
            }
        )


class _Text(serializers.CharField):
    """Text and nothing else: DRF would turn the number 5 into "5"."""

    def to_internal_value(self, data: Any) -> str:
        if not isinstance(data, str):
            self.fail("invalid")
        return super().to_internal_value(data)


class GenerateBody(serializers.Serializer[Any]):
    # The limit and the plain text are checked by the service; this only keeps absurd bodies out.
    note = _Text(max_length=4000, required=False, allow_blank=True, trim_whitespace=False)


class GenerateView(APIView):
    """Asks the user's own coach for a draft of a week. Synchronous: the answer can take up to
    a minute or two. The body may hold a ``note``: what the athlete wants the coach to know about
    the week. Nothing of it is repeated in an error but the fixed texts of its field."""

    throttle_classes = [PlanGenerateThrottle]
    http_method_names = ["post", "options"]

    def post(self, request: Request, week: str) -> Response:
        user = _user(request)
        monday = _monday(week)
        if monday is None:
            return _error(status.HTTP_404_NOT_FOUND, "week_not_plannable", NOT_PLANNABLE)
        body = GenerateBody(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            generated = generate(user, monday, body.validated_data.get("note", ""))
        except DjangoValidationError as error:
            raise serializers.ValidationError(error.message_dict) from None
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


class CheckView(APIView):
    """Runs the rules on a week plan that was changed by hand, and stores nothing: the page asks
    after every change. The body is a plan in the format of the plan (``docs/weekly-plan.md``), with
    an optional ``lineage`` per workout. The answer is the report and ``order``: for each workout
    as the findings number them, its place in the body (the findings follow the stored order, by
    day and time of day)."""

    http_method_names = ["post", "options"]

    def post(self, request: Request, week: str) -> Response:
        monday = _monday(week)
        if monday is None:
            return _error(status.HTTP_404_NOT_FOUND, "week_not_plannable", NOT_PLANNABLE)
        try:
            data = request.data
        except RecursionError:  # nesting that the JSON reader of the framework gave up on
            data = None
        try:
            checked = check(_user(request), monday, data)
        except WeekNotPlannable:
            return _error(status.HTTP_404_NOT_FOUND, "week_not_plannable", NOT_PLANNABLE)
        except PlanFormatError as error:
            return _error(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "invalid_plan",
                INVALID_PLAN,
                problems=[{"path": p.path, "message": p.message} for p in error.problems],
            )
        return Response({**report_data(checked.report), "order": list(checked.order)})


class ReviseView(APIView):
    """Stores a plan that was changed by hand as a new draft version of the week (the plan whose id
    is in the address is the version it was made from, and stays as it is). The body is the same as
    that of the check. The answer is the new draft with its checks, also if they have errors."""

    http_method_names = ["post", "options"]

    def post(self, request: Request, plan_id: UUID) -> Response:
        user = _user(request)
        try:
            data = request.data
        except RecursionError:  # nesting that the JSON reader of the framework gave up on
            data = None
        try:
            plan = revise(user, plan_id, data)
        except services.PlanNotFound:
            return _error(status.HTTP_404_NOT_FOUND, "not_found", NOT_FOUND)
        except PlanNotRevisable:
            return _error(status.HTTP_409_CONFLICT, "not_revisable", NOT_REVISABLE)
        except WeekNotPlannable:
            return _error(status.HTTP_404_NOT_FOUND, "week_not_plannable", NOT_PLANNABLE)
        except PlanFormatError as error:
            return _error(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "invalid_plan",
                INVALID_PLAN,
                problems=[{"path": p.path, "message": p.message} for p in error.problems],
            )
        response = _detail(user, plan)
        response.status_code = status.HTTP_201_CREATED
        return response


class RestoreView(APIView):
    """Brings back a version of a week that was replaced or discarded, as a new draft (the version
    in the address is not touched). The answer is the new draft with its checks as they are now."""

    http_method_names = ["post", "options"]

    def post(self, request: Request, plan_id: UUID) -> Response:
        user = _user(request)
        try:
            plan = restore(user, plan_id)
        except services.PlanNotFound:
            return _error(status.HTTP_404_NOT_FOUND, "not_found", NOT_FOUND)
        except PlanNotRestorable:
            return _error(status.HTTP_409_CONFLICT, "not_restorable", NOT_RESTORABLE)
        except WeekNotPlannable:
            return _error(status.HTTP_404_NOT_FOUND, "week_not_plannable", NOT_PLANNABLE)
        response = _detail(user, plan)
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
