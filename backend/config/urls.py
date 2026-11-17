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
    path("api/activities/", include("activities.urls")),
    path("api/athlete/", include("athletes.urls")),
    path("api/goals/", include("goals.urls")),
    path("api/availability/", include("availability.urls")),
    path("api/coach/", include("coach.urls")),
    path("api/planning/", include("planning.urls")),
    path("api/reviews/", include("reviews.urls")),
    path("api/season/", include("season.urls")),
    path("api/dashboard/", include("dashboard.urls")),
    path("api/chat/", include("chat.urls")),
]
