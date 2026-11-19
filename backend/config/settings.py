"""Django settings for PaceForge.

All instance configuration comes from environment variables (see ``.env.example``).
There are deliberately no insecure defaults for secrets.
"""

from pathlib import Path
from urllib.parse import urlsplit

import environ
from django.core.exceptions import ImproperlyConfigured

from coach.endpoints import parse_base_urls

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
    "integrations",
    "activities",
    "athletes",
    "goals",
    "availability",
    "wellness",
    "coach",
    "planning",
    "reviews",
    "season",
    "dashboard",
    "chat",
    "jobs",
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

# Where the Intervals.icu API lives. Only changed to point tests or development at a fake server.
INTERVALS_API_BASE_URL = env.str("INTERVALS_API_BASE_URL", default="https://intervals.icu/api/v1")
if urlsplit(INTERVALS_API_BASE_URL).scheme not in {"http", "https"}:
    raise ImproperlyConfigured("INTERVALS_API_BASE_URL must start with http:// or https://")
# How many weeks back an activity sync from Intervals.icu reads, up to today.
INTERVALS_SYNC_WEEKS = env.int("INTERVALS_SYNC_WEEKS", default=12)
if not 8 <= INTERVALS_SYNC_WEEKS <= 12:
    raise ImproperlyConfigured("INTERVALS_SYNC_WEEKS must be a whole number from 8 to 12")

# The background jobs. The scheduler syncs each user every JOBS_SYNC_HOURS hours. From
# JOBS_SUNDAY_HOUR o'clock on Sunday (in the user's time zone) it reviews the week and drafts the
# next one. It looks for due jobs every JOBS_INTERVAL_MINUTES minutes.
JOBS_SYNC_HOURS = env.int("JOBS_SYNC_HOURS", default=6)
if not 1 <= JOBS_SYNC_HOURS <= 24:
    raise ImproperlyConfigured("JOBS_SYNC_HOURS must be a whole number from 1 to 24")
JOBS_SUNDAY_HOUR = env.int("JOBS_SUNDAY_HOUR", default=18)
if not 0 <= JOBS_SUNDAY_HOUR <= 23:
    raise ImproperlyConfigured("JOBS_SUNDAY_HOUR must be a whole number from 0 to 23")
JOBS_INTERVAL_MINUTES = env.int("JOBS_INTERVAL_MINUTES", default=15)
if not 1 <= JOBS_INTERVAL_MINUTES <= 60:
    raise ImproperlyConfigured("JOBS_INTERVAL_MINUTES must be a whole number from 1 to 60")

# The AI providers: the OpenAI-compatible addresses (OpenAI itself, Ollama, llama.cpp ...) that
# users may choose from. Empty: none. Users cannot enter addresses of their own, so that the
# server cannot be pointed at internal systems.
AI_ALLOWED_BASE_URLS = parse_base_urls(
    "AI_ALLOWED_BASE_URLS", env.list("AI_ALLOWED_BASE_URLS", default=[])
)
# Where the Anthropic API lives. Only changed to point tests or development at a fake server.
(ANTHROPIC_API_BASE_URL,) = parse_base_urls(
    "ANTHROPIC_API_BASE_URL",
    [env.str("ANTHROPIC_API_BASE_URL", default="https://api.anthropic.com")],
)

# The largest activity file (FIT or TCX) that is accepted, in bytes, before it is even parsed.
ACTIVITY_UPLOAD_MAX_BYTES = env.int("ACTIVITY_UPLOAD_MAX_BYTES", default=25 * 1024 * 1024)
if ACTIVITY_UPLOAD_MAX_BYTES <= 0:
    raise ImproperlyConfigured("ACTIVITY_UPLOAD_MAX_BYTES must be a positive integer")

REST_FRAMEWORK = {
    # Session auth enforces CSRF for unsafe methods; every endpoint requires a login by default.
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    # Counters live in the process cache, like allauth's login limits (not shared by workers).
    "DEFAULT_THROTTLE_RATES": {
        "provider_connection": "10/min",
        "activity_import": "30/min",
        "coach_check": "10/min",
        "planning_generate": "5/min",
        "season_generate": "3/min",
        "planning_push": "10/min",
        "review_comment": "5/min",
        "chat": "10/min",
    },
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
# TOTP secrets and recovery-code seeds are stored encrypted (accounts/mfa_adapter.py).
MFA_ADAPTER = "accounts.mfa_adapter.MFAAdapter"
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
