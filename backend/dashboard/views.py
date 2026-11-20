from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from core.views import authenticated_user

from .overview import dashboard_of
from .serializers import dashboard_data


class DashboardView(APIView):
    """The start page in one request: the current week, the season, the main goal, the minutes of
    the last weeks, the latest activities and the use of the coach. Read only."""

    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "head", "options"]

    def get(self, request: Request) -> Response:
        user = authenticated_user(request)
        return Response(dashboard_data(dashboard_of(user)))
