from django.urls import path

from . import views

urlpatterns = [
    path("", views.AthleteView.as_view(), name="athlete"),
    path("sync/", views.SyncView.as_view(), name="athlete-sync"),
    path(
        "thresholds/<str:sport>/<str:metric>/",
        views.ThresholdView.as_view(),
        name="athlete-threshold",
    ),
]
