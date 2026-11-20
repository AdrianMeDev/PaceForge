"""Django settings for PaceForge.

All instance configuration comes from environment variables (see ``.env.example``).
There are deliberately no insecure defaults for secrets.
"""

import re
from ipaddress import IPv6Address
from pathlib import Path
from urllib.parse import urlsplit

import environ
from django.core.exceptions import ImproperlyConfigured

from coach.endpoints import parse_base_urls
from config.database import database_from_env

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
if not ENCRYPTION_KEYS:
    raise ImproperlyConfigured("ENCRYPTION_KEY must contain at least one key")
# Key for encrypted database backups (see core/backup_crypto.py). Optional: without it no backup
# is made. Several keys, comma separated: the first one encrypts, all of them decrypt. It must
# differ from every key of ENCRYPTION_KEY (decoded, so another spelling counts) and be kept apart
# from the backups. Enforced by check core.E007 and by load_backup_keys in core/backup.py.
BACKUP_ENCRYPTION_KEYS = [
    key.strip() for key in env.str("BACKUP_ENCRYPTION_KEY", default="").split(",") if key.strip()
]
# Where backups are written, how often the scheduler makes one, and how many are kept.
BACKUP_DIR = Path(env.str("BACKUP_DIR", default=str(BASE_DIR.parent / "backups")))
BACKUP_INTERVAL_HOURS = env.int("BACKUP_INTERVAL_HOURS", default=24)
if not 1 <= BACKUP_INTERVAL_HOURS <= 168:
    raise ImproperlyConfigured("BACKUP_INTERVAL_HOURS must be a whole number from 1 to 168")
BACKUP_KEEP_DAILY = env.int("BACKUP_KEEP_DAILY", default=7)
if not 1 <= BACKUP_KEEP_DAILY <= 365:
    raise ImproperlyConfigured("BACKUP_KEEP_DAILY must be a whole number from 1 to 365")
BACKUP_KEEP_WEEKLY = env.int("BACKUP_KEEP_WEEKLY", default=4)
if not 0 <= BACKUP_KEEP_WEEKLY <= 104:
    raise ImproperlyConfigured("BACKUP_KEEP_WEEKLY must be a whole number from 0 to 104")
# The public host name of the instance (no scheme, no path). It is the default for ALLOWED_HOSTS
# and, outside debug mode, for CSRF_TRUSTED_ORIGINS. Optional.
APP_DOMAIN = env.str("APP_DOMAIN", default="").strip().lower()
if APP_DOMAIN and not re.fullmatch(
    r"(?=.{1,253}$)[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)*",
    APP_DOMAIN,
):
    raise ImproperlyConfigured("APP_DOMAIN must be a host name only, without scheme, port or path")
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=[APP_DOMAIN] if APP_DOMAIN else [])

# Invitation links always use this configured origin, never the request's Host header.
APP_ORIGIN = env.str(
    "APP_ORIGIN",
    default=f"https://{APP_DOMAIN}" if APP_DOMAIN else ("http://localhost:4200" if DEBUG else ""),
).strip()
if APP_ORIGIN:
    try:
        _origin = urlsplit(APP_ORIGIN)
        _host = _origin.hostname or ""
        if ":" in _host:
            IPv6Address(_host)
            _host = f"[{_host}]"
        elif not re.fullmatch(
            r"(?=.{1,253}$)[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?"
            r"(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)*",
            _host,
        ):
            raise ValueError
        _port = _origin.port
        if (
            _origin.scheme not in {"http", "https"}
            or _origin.username is not None
            or _origin.password is not None
            or _origin.path not in {"", "/"}
            or "?" in APP_ORIGIN
            or "#" in APP_ORIGIN
            or any(character.isspace() for character in APP_ORIGIN)
            or any(ord(character) < 32 or ord(character) == 127 for character in APP_ORIGIN)
            or not re.fullmatch(re.escape(_host) + r"(?::[0-9]+)?", _origin.netloc, re.I)
            or _origin.netloc.endswith(":")
            or _port == 0
        ):
            raise ValueError
        APP_ORIGIN = f"{_origin.scheme}://{_host}" + (f":{_port}" if _port is not None else "")
    except ValueError as error:
        raise ImproperlyConfigured(
            "APP_ORIGIN must be an http:// or https:// origin with a host and optional port, "
            "without credentials, path, query or fragment"
        ) from error

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

DATABASES = {"default": database_from_env(env)}

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
CSRF_TRUSTED_ORIGINS = env.list(
    "DJANGO_CSRF_TRUSTED_ORIGINS",
    default=[f"https://{APP_DOMAIN}"] if APP_DOMAIN and not DEBUG else [],
)

# Behind an HTTPS reverse proxy (Caddy) the request arrives as plain HTTP. Trust the proxy's
# X-Forwarded-Proto header only when DJANGO_TRUST_PROXY_HEADERS=true (opt-in, off by default).
# Otherwise a client that reaches Django directly could spoof the scheme and the URLs built from it.
if env.bool("DJANGO_TRUST_PROXY_HEADERS", default=False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
ACCOUNT_DEFAULT_HTTP_PROTOCOL = "http" if DEBUG else "https"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
SECURE_HSTS_SECONDS = env.int("DJANGO_HSTS_SECONDS", default=0 if DEBUG else 31536000)
if SECURE_HSTS_SECONDS < 0:
    raise ImproperlyConfigured("DJANGO_HSTS_SECONDS must not be negative")

# Keep database connections open between requests and drop dead ones.
CONN_MAX_AGE = env.int("DATABASE_CONN_MAX_AGE", default=60)
if CONN_MAX_AGE < 0:
    raise ImproperlyConfigured("DATABASE_CONN_MAX_AGE must not be negative")
DATABASES["default"]["CONN_MAX_AGE"] = CONN_MAX_AGE
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True

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

# How long all the AI calls of one request (a plan, a change, a chat answer) may take together, in
# seconds. It must end before Gunicorn (GUNICORN_TIMEOUT, read by backend/entrypoint.sh) and the
# proxy give up on the request, or the answer is paid for and never arrives.
GUNICORN_TIMEOUT = env.int("GUNICORN_TIMEOUT", default=240)
AI_REQUEST_DEADLINE_SECONDS = env.int("AI_REQUEST_DEADLINE_SECONDS", default=210)
if not 0 < AI_REQUEST_DEADLINE_SECONDS < GUNICORN_TIMEOUT:
    raise ImproperlyConfigured(
        "AI_REQUEST_DEADLINE_SECONDS must be a whole number above 0 and below GUNICORN_TIMEOUT"
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
        "account_export": "5/min",
        "account_delete": "5/min",
    },
}

# Invitation emails, counted in the database so every worker shares the numbers:
# per sending administrator and per recipient address.
INVITATION_EMAIL_LIMITS = {
    "sender": {"limit": 20, "window_seconds": 60},
    "recipient": {"limit": 5, "window_seconds": 3600},
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

# Container-friendly logging: warnings and unhandled request errors go to stderr.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"}},
    "handlers": {
        "stderr": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stderr",
            "formatter": "plain",
        },
    },
    "root": {"handlers": ["stderr"], "level": "WARNING"},
    "loggers": {"django.request": {"handlers": ["stderr"], "level": "ERROR", "propagate": False}},
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
