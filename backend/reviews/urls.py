from django.urls import path

from . import views

urlpatterns = [
    path("weeks/", views.WeeksView.as_view(), name="reviews-weeks"),
    path("weeks/<str:week>/", views.WeekView.as_view(), name="reviews-week"),
    path(
        "weeks/<str:week>/workouts/<uuid:workout_id>/",
        views.CorrectionView.as_view(),
        name="reviews-correction",
    ),
    path("weeks/<str:week>/feedback/", views.FeedbackView.as_view(), name="reviews-feedback"),
]
