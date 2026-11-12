from rest_framework.routers import DefaultRouter

from core.tests.sample.views import NoteViewSet, UnscopedViewSet

router = DefaultRouter()
router.register("notes", NoteViewSet, basename="note")
router.register("unscoped", UnscopedViewSet, basename="unscoped")

urlpatterns = router.urls
