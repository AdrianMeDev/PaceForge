from django.urls import path

from accounts import views

urlpatterns = [
    path("invitations/", views.InvitationListCreateView.as_view(), name="invitation-list"),
    path(
        "invitations/<uuid:pk>/resend/",
        views.InvitationResendView.as_view(),
        name="invitation-resend",
    ),
    path(
        "invitations/<uuid:pk>/revoke/",
        views.InvitationRevokeView.as_view(),
        name="invitation-revoke",
    ),
]
