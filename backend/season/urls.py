from django.urls import path

from . import views

urlpatterns = [
    path("", views.SeasonView.as_view(), name="season"),
    path("reassessment/", views.ReassessmentView.as_view(), name="season-reassessment"),
    path("plans/", views.PlansView.as_view(), name="season-plans"),
    path("plans/generate/", views.GenerateView.as_view(), name="season-generate"),
    path("plans/<uuid:plan_id>/", views.PlanView.as_view(), name="season-plan"),
    path("plans/<uuid:plan_id>/confirm/", views.ConfirmView.as_view(), name="season-confirm"),
    path("plans/<uuid:plan_id>/discard/", views.DiscardView.as_view(), name="season-discard"),
    path("plans/<uuid:plan_id>/change/", views.ChangeView.as_view(), name="season-change"),
    path("plans/<uuid:plan_id>/restore/", views.RestoreView.as_view(), name="season-restore"),
]
