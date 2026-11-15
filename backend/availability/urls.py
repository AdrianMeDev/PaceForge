from django.urls import include, path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("periods", views.PeriodViewSet, basename="period")
router.register("limitations", views.LimitationViewSet, basename="limitation")

urlpatterns = [
    path("", views.AvailabilityView.as_view(), name="availability"),
    path("", include(router.urls)),
]
