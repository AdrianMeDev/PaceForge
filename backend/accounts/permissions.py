from typing import Any

from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission
from rest_framework.request import Request

from accounts.services.mfa import has_totp

MFA_REQUIRED_MESSAGE = "Two-factor authentication must be turned on for administrators."


class IsMfaAdmin(BasePermission):
    """Administrators with an active authenticator app (TOTP).

    Anyone who is not an administrator gets the plain 403 of ``IsAdminUser``. An administrator
    without TOTP gets a 403 whose body carries ``"code": "mfa_required"``, so that the SPA can
    send them to the security page instead of showing a generic error.

    There is deliberately no ``message`` attribute: DRF would use it for every refusal, and
    members must not be told about the rules for administrators.
    """

    def has_permission(self, request: Request, view: Any) -> bool:
        user = request.user
        if not (user and user.is_authenticated and user.is_staff):
            return False
        if has_totp(user):
            return True
        raise PermissionDenied({"detail": MFA_REQUIRED_MESSAGE, "code": "mfa_required"})
