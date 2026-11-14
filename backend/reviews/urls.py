from django.urls import path

from . import views

urlpatterns = [
    path("weeks/", views.WeeksView.as_view(), name="reviews-weeks"),
    path("weeks/<str:week>/", views.WeekView.as_view(), name="reviews-week"),
]
