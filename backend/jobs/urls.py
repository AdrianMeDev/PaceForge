from django.urls import path

from . import views

urlpatterns = [
    path("settings/", views.JobSettingsView.as_view(), name="jobs-settings"),
    path("runs/", views.JobRunsView.as_view(), name="jobs-runs"),
]
