from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User

from . import pricing, services
from .models import EFFORT_FIELDS, AIModelPrice
from .providers.base import (
    DeadlineExceededError,
    EndpointNotAllowedError,
    InvalidKeyError,
    ProviderError,
    ProviderUnavailableError,
    RateLimitedError,
)
from .serializers import ModelPriceInput, ProviderInput, costs_state, provider_state
from .throttles import CoachCheckThrottle

# Fixed texts: nothing the provider said, and nothing that was sent, goes into an answer.
PROBLEMS = {
    "invalid_key": "The provider did not accept the key. Check that you copied all of it.",
    "rate_limited": "The provider is asking to slow down. Please try again in a moment.",
    "unavailable": "The provider cannot be reached right now. Please try again later.",
    "too_slow": "The coach did not finish in time. Choose a lower effort or a faster model for "
    "this task, or try again.",
    "unexpected": "The provider answered in an unexpected way. Check the model name and try again.",
    "not_allowed": "This address is no longer allowed on this server. Choose another one.",
}


def _user(request: Request) -> User:
    assert isinstance(request.user, User)  # IsAuthenticated is the default permission
    return request.user


class ProviderView(APIView):
    """The signed-in user's own AI provider; there is no id and no user parameter."""

    http_method_names = ["get", "put", "delete", "head", "options"]

    def get(self, request: Request) -> Response:
        return Response(provider_state(_user(request)))

    def put(self, request: Request) -> Response:
        user = _user(request)
        serializer = ProviderInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            services.save_configuration(
                user,
                provider=data["provider"],
                model=data["model"],
                season_model=data.get("season_model", ""),
                week_model=data.get("week_model", ""),
                chat_model=data.get("chat_model", ""),
                efforts={name: data.get(name, "") for name in EFFORT_FIELDS},
                base_url=data.get("base_url", ""),
                api_key=data.get("api_key"),
            )
        except DjangoValidationError as error:
            raise serializers.ValidationError(error.message_dict) from None
        return Response(provider_state(user))

    def delete(self, request: Request) -> Response:
        services.remove_configuration(_user(request))
        return Response(status=status.HTTP_204_NO_CONTENT)


class CostsView(APIView):
    """The signed-in user's prices and monthly costs."""

    http_method_names = ["get", "head", "options"]

    def get(self, request: Request) -> Response:
        return Response(costs_state(_user(request)))


class ModelPricesView(APIView):
    """Sets the price of one model: a new model gets a price, a known one is replaced."""

    http_method_names = ["put", "options"]

    def put(self, request: Request) -> Response:
        user = _user(request)
        serializer = ModelPriceInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            pricing.save_price(
                user,
                data["model"],
                data["input_per_million"],
                data["output_per_million"],
                data.get("cached_per_million"),
            )
        except DjangoValidationError as error:
            raise serializers.ValidationError(error.message_dict) from None
        except pricing.PriceLimitError:
            raise serializers.ValidationError(
                {"model": ["You cannot keep more prices. Remove one first."]}
            ) from None
        return Response(costs_state(user))


class ModelPriceDetailView(APIView):
    http_method_names = ["delete", "options"]

    def delete(self, request: Request, price_id: int) -> Response:
        deleted, _ = AIModelPrice.objects.for_user(_user(request)).filter(pk=price_id).delete()
        if not deleted:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProviderCheckView(APIView):
    """Sends a tiny fixed prompt with the user's own key. The check itself always answers 200
    with the new state and what came of it; only a missing setup is an error."""

    throttle_classes = [CoachCheckThrottle]
    http_method_names = ["post", "options"]

    def post(self, request: Request) -> Response:
        user = _user(request)
        problem: str | None = None
        retry_after: int | None = None
        try:
            services.check(user)
        except services.NotConfiguredError:
            return Response(
                {"detail": "No AI provider is set up."}, status=status.HTTP_404_NOT_FOUND
            )
        except InvalidKeyError:
            problem = "invalid_key"
        except RateLimitedError as error:
            problem, retry_after = "rate_limited", error.retry_after
        except ProviderUnavailableError:
            problem = "unavailable"
        except EndpointNotAllowedError:
            problem = "not_allowed"
        except ProviderError:
            problem = "unexpected"
        answer: dict[str, Any] = provider_state(user)
        answer["check"] = {
            "ok": problem is None,
            "problem": problem,
            "message": PROBLEMS[problem] if problem else "",
            "retry_after": retry_after,
        }
        return Response(answer)


def provider_problem(error: ProviderError) -> Response:
    """The answer to a provider error that stopped a request of the user: a status and a fixed text
    with a code the client can act on, never what the provider said."""
    if isinstance(error, InvalidKeyError):
        return _problem(status.HTTP_502_BAD_GATEWAY, "invalid_key")
    if isinstance(error, RateLimitedError):
        response = _problem(
            status.HTTP_429_TOO_MANY_REQUESTS, "rate_limited", retry_after=error.retry_after
        )
        if error.retry_after is not None:
            response["Retry-After"] = str(error.retry_after)
        return response
    if isinstance(error, DeadlineExceededError):
        return _problem(status.HTTP_503_SERVICE_UNAVAILABLE, "too_slow")
    if isinstance(error, ProviderUnavailableError):
        return _problem(status.HTTP_503_SERVICE_UNAVAILABLE, "unavailable")
    if isinstance(error, EndpointNotAllowedError):
        return _problem(status.HTTP_502_BAD_GATEWAY, "not_allowed")
    return _problem(status.HTTP_502_BAD_GATEWAY, "unexpected")


def _problem(http_status: int, code: str, **extra: Any) -> Response:
    return Response({"detail": PROBLEMS[code], "code": code, **extra}, status=http_status)
