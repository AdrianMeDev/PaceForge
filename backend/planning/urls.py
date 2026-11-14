from django.urls import path

from . import views

urlpatterns = [
    path("weeks/", views.WeeksView.as_view(), name="planning-weeks"),
    path("weeks/<str:week>/generate/", views.GenerateView.as_view(), name="planning-generate"),
    path("plans/<uuid:plan_id>/", views.PlanView.as_view(), name="planning-plan"),
    path("plans/<uuid:plan_id>/confirm/", views.ConfirmView.as_view(), name="planning-confirm"),
    path("plans/<uuid:plan_id>/push/", views.PushView.as_view(), name="planning-push"),
    path("plans/<uuid:plan_id>/discard/", views.DiscardView.as_view(), name="planning-discard"),
]
