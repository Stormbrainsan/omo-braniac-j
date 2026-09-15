import os
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# --------------------------------------------------------------------------
# Core
# --------------------------------------------------------------------------
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "insecure-dev-key-change-me")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "*").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # third party
    "rest_framework",
    "rest_framework_simplejwt",
    "drf_spectacular",
    "django_filters",
    # local
    "accounts",
    "audit",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# --------------------------------------------------------------------------
# Database
# --------------------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "tses_otp"),
        "USER": os.environ.get("POSTGRES_USER", "tses"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "tses"),
        "HOST": os.environ.get("POSTGRES_HOST", "db"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --------------------------------------------------------------------------
# i18n
# --------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --------------------------------------------------------------------------
# Redis (raw client, used directly for OTP storage / rate limiting, NOT
# Django's cache framework — we need fine-grained control over TTLs, atomic
# INCR/EXPIRE, and Lua-based get-and-delete for one-time OTP consumption).
# --------------------------------------------------------------------------
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")

# --------------------------------------------------------------------------
# Celery
# --------------------------------------------------------------------------
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://redis:6379/1")
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "redis://redis:6379/2")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
# Keep broker connection retries on startup so a slow-to-boot Redis container
# doesn't crash the worker in docker-compose.
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
# If the broker is briefly unavailable when .delay() is called, retry a few
# times client-side before we give up and fall back (see accounts/services.py).
CELERY_TASK_PUBLISH_RETRY = True
CELERY_TASK_PUBLISH_RETRY_POLICY = {
    "max_retries": 2,
    "interval_start": 0,
    "interval_step": 0.2,
    "interval_max": 0.5,
}

# --------------------------------------------------------------------------
# DRF / JWT / Spectacular
# --------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_FILTER_BACKENDS": ("django_filters.rest_framework.DjangoFilterBackend",),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_CLASSES": (),
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": False,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

SPECTACULAR_SETTINGS = {
    "TITLE": "TSES OTP Authentication Service",
    "DESCRIPTION": (
        "Email-based OTP authentication service: request/verify OTP, "
        "JWT issuance, and an audited log of authentication events."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

# --------------------------------------------------------------------------
# OTP configuration
# --------------------------------------------------------------------------
OTP_TTL_SECONDS = int(os.environ.get("OTP_TTL_SECONDS", 300))
OTP_REQUEST_MAX_PER_EMAIL = int(os.environ.get("OTP_REQUEST_MAX_PER_EMAIL", 3))
OTP_REQUEST_WINDOW_EMAIL_SECONDS = int(os.environ.get("OTP_REQUEST_WINDOW_EMAIL_SECONDS", 600))
OTP_REQUEST_MAX_PER_IP = int(os.environ.get("OTP_REQUEST_MAX_PER_IP", 10))
OTP_REQUEST_WINDOW_IP_SECONDS = int(os.environ.get("OTP_REQUEST_WINDOW_IP_SECONDS", 3600))
OTP_MAX_FAILED_ATTEMPTS = int(os.environ.get("OTP_MAX_FAILED_ATTEMPTS", 5))
OTP_LOCKOUT_WINDOW_SECONDS = int(os.environ.get("OTP_LOCKOUT_WINDOW_SECONDS", 900))

# Whether test@gmail.com and test+work@gmail.com should resolve to the same
# account. Default OFF — see README "Email normalization" for the reasoning.
NORMALIZE_GMAIL_PLUS_ALIAS = os.environ.get("NORMALIZE_GMAIL_PLUS_ALIAS", "0") == "1"

# --------------------------------------------------------------------------
# Logging — audit/email "sending" happens via logger output per the brief
# ("log output is sufficient from the worker").
# --------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "otp": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}
