from django.urls import path

from . import views

urlpatterns = [
    path("", views.AvailabilityView.as_view(), name="availability"),
]
