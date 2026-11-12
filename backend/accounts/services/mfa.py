from allauth.mfa.models import Authenticator
from allauth.mfa.utils import is_mfa_enabled

from accounts.models import User


def has_totp(user: User) -> bool:
    """Whether ``user`` has an active authenticator app.

    Recovery codes alone deliberately do not count: ``is_mfa_enabled`` without a type filter
    would also accept them, and they are only a fallback for a second factor that exists.
    """
    return is_mfa_enabled(user, [Authenticator.Type.TOTP])
