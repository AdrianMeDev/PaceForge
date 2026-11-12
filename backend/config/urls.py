from django.http import HttpRequest, JsonResponse
from django.urls import include, path

from accounts.views import MeView


def health(request: HttpRequest) -> JsonResponse:
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("api/health/", health, name="health"),
    path("api/auth/", include("allauth.headless.urls")),
    path("api/me/", MeView.as_view(), name="me"),
    path("api/admin/", include("accounts.urls")),
    path("api/integrations/", include("integrations.urls")),
]
