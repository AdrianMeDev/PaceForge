"""Django settings for PaceForge.

All instance configuration comes from environment variables (see ``.env.example``).
There are deliberately no insecure defaults for secrets.
"""

from pathlib import Path

import environ
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env()
_env_file = BASE_DIR.parent / ".env"
if _env_file.is_file():
    environ.Env.read_env(_env_file)

SECRET_KEY = env.str("DJANGO_SECRET_KEY")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
# Instance key for secrets stored in the database (see core/encryption.py). Required, no default.
# Several keys, comma separated: the first one encrypts, all of them decrypt (key rotation).
# Keep it apart from database backups.
ENCRYPTION_KEYS = [key.strip() for key in env.str("ENCRYPTION_KEY").split(",") if key.strip()]
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=[])

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "rest_framework",
    "allauth",
    "allauth.account",
    "allauth.mfa",
    "allauth.headless",
    "accounts",
    "core",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        # Our own templates (e.g. mail texts) take precedence over those of installed apps.
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {"default": env.db("DATABASE_URL")}

AUTH_USER_MODEL = "accounts.User"

# Argon2id first; the Django defaults stay as fallbacks so older hashes still verify.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.ScryptPasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Sessions and CSRF: server-side sessions in HttpOnly cookies, no tokens in the browser.
# The SPA reads the (non-HttpOnly) CSRF cookie and echoes it in the X-CSRFToken header.
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])

# closed: nobody can register; invite_only: registration needs a valid invitation token;
# open: public registration (not intended for the MVP).
REGISTRATION_MODE = env.str("REGISTRATION_MODE", default="invite_only")
if REGISTRATION_MODE not in {"closed", "invite_only", "open"}:
    raise ImproperlyConfigured(f"Invalid REGISTRATION_MODE: {REGISTRATION_MODE!r}")
INVITATION_TTL_DAYS = env.int("INVITATION_TTL_DAYS", default=7)

REST_FRAMEWORK = {
    # Session auth enforces CSRF for unsafe methods; every endpoint requires a login by default.
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
}

# allauth: email + password, headless API for the SPA (browser client only).
AUTHENTICATION_BACKENDS = ["allauth.account.auth_backends.AuthenticationBackend"]
ACCOUNT_ADAPTER = "accounts.adapters.AccountAdapter"
ACCOUNT_SIGNUP_FORM_CLASS = "accounts.forms.InvitationSignupForm"
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*"]
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_EMAIL_VERIFICATION = "mandatory"
ACCOUNT_LOGOUT_ON_PASSWORD_CHANGE = True
# Second factor: authenticator app (TOTP) plus recovery codes. WebAuthn/passkeys stay off.
MFA_SUPPORTED_TYPES = ["totp", "recovery_codes"]
MFA_TOTP_ISSUER = "PaceForge"
# The "app" client is CSRF-exempt and token based; only the cookie-based client is enabled.
HEADLESS_CLIENTS = ("browser",)
HEADLESS_ONLY = True
HEADLESS_FRONTEND_URLS = {
    "account_confirm_email": "/account/verify-email/{key}",
    "account_reset_password": "/account/password/reset",
    "account_reset_password_from_key": "/account/password/reset/key/{key}",
    "account_signup": "/account/signup",
}

DEFAULT_FROM_EMAIL = env.str("DEFAULT_FROM_EMAIL", default="PaceForge <noreply@localhost>")
_smtp_host = env.str("SMTP_HOST", default="")
if _smtp_host:
    MAILERS = {
        "default": {
            "BACKEND": "django.core.mail.backends.smtp.EmailBackend",
            "OPTIONS": {
                "host": _smtp_host,
                "port": env.int("SMTP_PORT", default=587),
                "username": env.str("SMTP_USERNAME", default=""),
                "password": env.str("SMTP_PASSWORD", default=""),
                "use_tls": env.bool("SMTP_USE_TLS", default=True),
            },
        },
    }
else:
    MAILERS = {"default": {"BACKEND": "django.core.mail.backends.console.EmailBackend"}}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
