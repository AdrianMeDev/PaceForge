from django.urls import path

from . import views

urlpatterns = [
    path("", views.SeasonView.as_view(), name="season"),
]
