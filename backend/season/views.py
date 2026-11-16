from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User

from .inputs import skeleton_for
from .serializers import skeleton_data


class SeasonView(APIView):
    """The skeleton of the signed-in user's season. It is worked out on every request from what
    the user has now and stored nowhere; there is no id and no user parameter."""

    def get(self, request: Request) -> Response:
        user = request.user
        assert isinstance(user, User)  # IsAuthenticated is the default permission
        return Response(skeleton_data(skeleton_for(user)))
