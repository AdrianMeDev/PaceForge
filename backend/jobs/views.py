from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User

from . import services
from .models import JobRun
from .serializers import JobSettingsInput, run_data, settings_data

RUN_LOG_LIMIT = 50


def _user(request: Request) -> User:
    assert isinstance(request.user, User)  # IsAuthenticated is the default permission
    return request.user


class JobSettingsView(APIView):
    """The signed-in user's own job toggles; the row is created on the first PATCH."""

    http_method_names = ["get", "patch", "head", "options"]

    def get(self, request: Request) -> Response:
        return Response(settings_data(services.settings_of(_user(request))))

    def patch(self, request: Request) -> Response:
        user = _user(request)
        serializer = JobSettingsInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        settings = services.settings_of(user)
        changed: list[str] = []
        for field, value in serializer.validated_data.items():
            setattr(settings, field, value)
            changed.append(field)
        if settings._state.adding:
            settings.save()
        else:
            settings.save(update_fields=[*changed, "updated_at"])
        return Response(settings_data(settings))


class JobRunsView(APIView):
    """The signed-in user's newest 50 job runs."""

    http_method_names = ["get", "head", "options"]

    def get(self, request: Request) -> Response:
        runs = JobRun.objects.for_user(_user(request))[:RUN_LOG_LIMIT]
        return Response([run_data(run) for run in runs])
