from rest_framework.routers import DefaultRouter

from core.tests.sample.views import NoteViewSet, UnscopedViewSet, WritableOwnerNoteViewSet

router = DefaultRouter()
router.register("notes", NoteViewSet, basename="note")
router.register("writable-owner-notes", WritableOwnerNoteViewSet, basename="writable-owner-note")
router.register("unscoped", UnscopedViewSet, basename="unscoped")

urlpatterns = router.urls
