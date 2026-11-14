import re
from datetime import date

from django.db.models import Count
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from planning.models import WeeklyPlan

from .models import WeekFeedback
from .serializers import review_data, week_list_data
from .services import WeekNotReviewable, reviewable_weeks, week_review

# Fixed texts, with a code the client can act on: nothing of the request goes into an error.
NOT_REVIEWABLE = "This week cannot be reviewed."

_WEEK = re.compile(r"\d{4}-\d{2}-\d{2}")


def _user(request: Request) -> User:
    assert isinstance(request.user, User)  # IsAuthenticated is the default permission
    return request.user


def _error(http_status: int, code: str, detail: str) -> Response:
    return Response({"detail": detail, "code": code}, status=http_status)


def parse_week(text: str) -> date | None:
    """The date in ``text`` if it is written ``YYYY-MM-DD`` and is a real day, else ``None``."""
    if not _WEEK.fullmatch(text):
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


class WeeksView(APIView):
    """The weeks that can be reviewed, with whether each has a confirmed plan and feedback."""

    http_method_names = ["get", "head", "options"]

    def get(self, request: Request) -> Response:
        user = _user(request)
        weeks = reviewable_weeks(user)
        counts: dict[date, int] = dict(
            WeeklyPlan.objects.for_user(user)
            .filter(week_start__in=weeks, status=WeeklyPlan.Status.CONFIRMED)
            .annotate(workout_count=Count("workouts"))
            .values_list("week_start", "workout_count")
        )
        with_feedback = set(
            WeekFeedback.objects.for_user(user)
            .filter(week_start__in=weeks)
            .values_list("week_start", flat=True)
        )
        return Response(week_list_data(weeks, counts, with_feedback))


class WeekView(APIView):
    """One week: the confirmed plan with the match of the activities, the comparison and the
    feedback."""

    http_method_names = ["get", "head", "options"]

    def get(self, request: Request, week: str) -> Response:
        monday = parse_week(week)
        if monday is None:
            return _error(status.HTTP_404_NOT_FOUND, "week_not_reviewable", NOT_REVIEWABLE)
        try:
            review = week_review(_user(request), monday)
        except WeekNotReviewable:
            return _error(status.HTTP_404_NOT_FOUND, "week_not_reviewable", NOT_REVIEWABLE)
        return Response(review_data(review))
