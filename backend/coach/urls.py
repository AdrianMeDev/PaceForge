from django.urls import path

from . import views

urlpatterns = [
    path("provider/", views.ProviderView.as_view(), name="coach-provider"),
    path("provider/check/", views.ProviderCheckView.as_view(), name="coach-provider-check"),
]
