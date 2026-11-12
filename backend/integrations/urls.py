from django.urls import path

from integrations import views

urlpatterns = [
    path("intervals/", views.IntervalsConnectionView.as_view(), name="intervals-connection"),
    path("intervals/check/", views.IntervalsCheckView.as_view(), name="intervals-check"),
]
