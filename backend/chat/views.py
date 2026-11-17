from django.core.exceptions import ValidationError
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import BaseThrottle
from rest_framework.views import APIView

from accounts.models import User
from coach.providers.base import ProviderError
from coach.services import NotConfiguredError
from coach.views import provider_problem

from .serializers import messages_data
from .services import clear, history, send
from .throttles import ChatThrottle

# Fixed texts, with a code the client can act on: nothing of the request goes into an error.
NOT_CONFIGURED = "No AI provider is set up."
NO_TEXT = "Write a message."


def _user(request: Request) -> User:
    assert isinstance(request.user, User)  # IsAuthenticated is the default permission
    return request.user


class MessagesView(APIView):
    """The conversation of the user with their coach: read it, write to the coach, delete it.

    Writing is synchronous: the answer can take a minute or two. The answer is the two messages
    that were stored (the athlete's and the coach's), the coach's with the draft it made, if any.
    """

    def get_throttles(self) -> list[BaseThrottle]:
        return [ChatThrottle()] if self.request.method == "POST" else []

    http_method_names = ["get", "post", "delete", "head", "options"]

    def get(self, request: Request) -> Response:
        return Response(messages_data(history(_user(request))))

    def post(self, request: Request) -> Response:
        text = request.data.get("text") if isinstance(request.data, dict) else None
        if not isinstance(text, str):
            return Response(
                {"detail": NO_TEXT, "code": "invalid", "errors": [NO_TEXT]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            sent = send(_user(request), text)
        except ValidationError as error:
            return Response(
                {"detail": error.messages[0], "code": "invalid", "errors": error.messages},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except NotConfiguredError:
            return Response(
                {"detail": NOT_CONFIGURED, "code": "not_configured"},
                status=status.HTTP_409_CONFLICT,
            )
        except ProviderError as error:
            return provider_problem(error)
        return Response(messages_data([sent.athlete, sent.coach]), status=status.HTTP_201_CREATED)

    def delete(self, request: Request) -> Response:
        clear(_user(request))
        return Response(status=status.HTTP_204_NO_CONTENT)
