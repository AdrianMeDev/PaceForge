from typing import TYPE_CHECKING, Any

from django.contrib.auth.base_user import BaseUserManager

if TYPE_CHECKING:
    from .models import User


def _clean_email(email: str | None) -> str:
    """Emails are stored lower-cased and trimmed so lookups and logins are case-insensitive."""
    return (email or "").strip().lower()


class UserManager(BaseUserManager["User"]):
    def _create_user(self, email: str, password: str | None, **extra_fields: Any) -> User:
        email = _clean_email(email)
        if not email:
            raise ValueError("An email address is required.")
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra_fields: Any) -> User:
        extra_fields.setdefault("is_staff", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(
        self, email: str, password: str | None = None, **extra_fields: Any
    ) -> User:
        """Create an administrator. The admin role is ``is_staff``."""
        extra_fields["is_staff"] = True
        return self._create_user(email, password, **extra_fields)

    def get_by_natural_key(self, username: str | None) -> User:
        return self.get(email=_clean_email(username))
