from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User

from .overview import dashboard_of
from .serializers import dashboard_data


class DashboardView(APIView):
    """The start page in one request: the current week, the season, the main goal, the minutes of
    the last weeks, the latest activities and the use of the coach. Read only."""

    http_method_names = ["get", "head", "options"]

    def get(self, request: Request) -> Response:
        assert isinstance(request.user, User)  # IsAuthenticated is the default permission
        return Response(dashboard_data(dashboard_of(request.user)))
