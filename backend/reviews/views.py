import re
from datetime import date
from uuid import UUID

from django.db.models import Count
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from planning.models import WeeklyPlan

from .models import WeekFeedback
from .serializers import CorrectionSerializer, FeedbackSerializer, review_data, week_list_data
from .services import (
    ActivityLinkedElsewhere,
    ActivityNotInWeek,
    StatusNeedsAnActivity,
    WeekNotReviewable,
    WorkoutNotFound,
    correct,
    reviewable_weeks,
    save_feedback,
    week_review,
)

# Fixed texts, with a code the client can act on: nothing of the request goes into an error.
NOT_REVIEWABLE = "This week cannot be reviewed."
NO_SUCH_WORKOUT = "There is no such workout in this week."
ACTIVITY_NOT_IN_WEEK = "Choose an activity of this week."
ACTIVITY_TAKEN = "This activity is already assigned to another workout."
STATUS_NEEDS_AN_ACTIVITY = "This status needs an activity. Link one first."

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


class CorrectionView(APIView):
    """Sets what the user decides about one workout: which activity belongs to it (or none), and
    how it went. Replaces an earlier decision; empty goes back to the automatic match. The answer
    is the whole week."""

    http_method_names = ["put", "options"]

    def put(self, request: Request, week: str, workout_id: UUID) -> Response:
        monday = parse_week(week)
        if monday is None:
            return _error(status.HTTP_404_NOT_FOUND, "week_not_reviewable", NOT_REVIEWABLE)
        form = CorrectionSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        data = form.validated_data
        try:
            review = correct(
                _user(request),
                monday,
                workout_id,
                activity_id=data["activity"],
                no_activity=data["no_activity"],
                status=data["status"],
            )
        except WeekNotReviewable:
            return _error(status.HTTP_404_NOT_FOUND, "week_not_reviewable", NOT_REVIEWABLE)
        except WorkoutNotFound:
            return _error(status.HTTP_404_NOT_FOUND, "workout_not_found", NO_SUCH_WORKOUT)
        except ActivityNotInWeek:
            return Response(
                {"activity": [ACTIVITY_NOT_IN_WEEK]}, status=status.HTTP_400_BAD_REQUEST
            )
        except ActivityLinkedElsewhere:
            return _error(status.HTTP_409_CONFLICT, "activity_taken", ACTIVITY_TAKEN)
        except StatusNeedsAnActivity:
            return Response(
                {"status": [STATUS_NEEDS_AN_ACTIVITY]}, status=status.HTTP_400_BAD_REQUEST
            )
        return Response(review_data(review))


class FeedbackView(APIView):
    """Sets the feedback on a week (replacing an earlier one; nothing in it removes it). The
    answer is the whole week."""

    http_method_names = ["put", "options"]

    def put(self, request: Request, week: str) -> Response:
        monday = parse_week(week)
        if monday is None:
            return _error(status.HTTP_404_NOT_FOUND, "week_not_reviewable", NOT_REVIEWABLE)
        form = FeedbackSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        try:
            review = save_feedback(_user(request), monday, **form.validated_data)
        except WeekNotReviewable:
            return _error(status.HTTP_404_NOT_FOUND, "week_not_reviewable", NOT_REVIEWABLE)
        return Response(review_data(review))
