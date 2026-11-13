from django.urls import include, path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("", views.ActivityViewSet, basename="activity")

urlpatterns = [
    # Before the router, so that "import" is never taken for an activity id.
    path("import/", views.ActivityImportView.as_view(), name="activity-import"),
    path("", include(router.urls)),
]
