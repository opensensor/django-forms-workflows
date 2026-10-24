"""
Django settings for example project.

This is a minimal example showing how to configure Django Form Workflows.
"""

import os
from pathlib import Path

import django
from django.core.exceptions import ImproperlyConfigured

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Explicitly opt into local development. Production fails closed without a secret.
DEBUG = os.environ.get("DJANGO_DEBUG", "0") == "1"
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured(
            "Set DJANGO_SECRET_KEY, or DJANGO_DEBUG=1 for local development."
        )
    SECRET_KEY = "django-insecure-example-development-only"
ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if host.strip()
]
SECURE_SSL_REDIRECT = not DEBUG
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_HSTS_SECONDS = 0 if DEBUG else 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = (
    os.environ.get("DJANGO_HSTS_INCLUDE_SUBDOMAINS", "0") == "1"
)
SECURE_HSTS_PRELOAD = os.environ.get("DJANGO_HSTS_PRELOAD", "0") == "1"
if not DEBUG:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": os.environ.get("DJANGO_CACHE_URL", "redis://127.0.0.1:6379/1"),
        }
    }

# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Required dependencies
    "nested_admin",
    "crispy_forms",
    "crispy_bootstrap5",
    # Django Form Workflows
    "django_forms_workflows.apps.DjangoFormsWorkflowsConfig",
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

ROOT_URLCONF = "example.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
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

WSGI_APPLICATION = "example.wsgi.application"

# Database
# https://docs.djangoproject.com/en/5.1/ref/settings/#databases

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# Password validation
# https://docs.djangoproject.com/en/5.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# Internationalization
# https://docs.djangoproject.com/en/5.1/topics/i18n/

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.1/howto/static-files/

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]


# Media files
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# Default primary key field type
# https://docs.djangoproject.com/en/5.1/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Crispy Forms Configuration
CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"
CRISPY_TEMPLATE_PACK = "bootstrap5"

# Django Form Workflows Configuration
# These are optional - the package works with sensible defaults

# LDAP Configuration (optional - only if using LDAP)
# FORMS_WORKFLOWS_LDAP_ATTR_MAP = {
#     'first_name': 'givenName',
#     'last_name': 'sn',
#     'email': 'mail',
#     'profile.department': 'department',
#     'profile.title': 'title',
# }
# FORMS_WORKFLOWS_LDAP_SYNC_GROUPS = True
# FORMS_WORKFLOWS_LDAP_PROFILE_MODEL = 'django_forms_workflows.UserProfile'

# Celery Configuration (optional - only if using async tasks)
# CELERY_BROKER_URL = 'redis://localhost:6379/0'
# CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'

# Email Configuration (for notifications)
# EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'  # For development
# For production, configure SMTP:
# EMAIL_HOST = 'smtp.example.com'
# EMAIL_PORT = 587
# EMAIL_USE_TLS = True
# EMAIL_HOST_USER = 'your-email@example.com'
# EMAIL_HOST_PASSWORD = 'your-password'
# DEFAULT_FROM_EMAIL = 'noreply@example.com'
# Console delivery is development-only; production uses explicit SMTP options.
_email_backend = (
    "django.core.mail.backends.console.EmailBackend"
    if DEBUG
    else "django.core.mail.backends.smtp.EmailBackend"
)
_smtp_options = {
    "host": os.environ.get("DJANGO_EMAIL_HOST", "localhost"),
    "port": int(os.environ.get("DJANGO_EMAIL_PORT", "587")),
    "username": os.environ.get("DJANGO_EMAIL_USER", ""),
    "password": os.environ.get("DJANGO_EMAIL_PASSWORD", ""),
    "use_tls": os.environ.get("DJANGO_EMAIL_USE_TLS", "1") == "1",
    "timeout": 10,
}
if django.VERSION >= (6, 1):
    MAILERS = {
        "default": {
            "BACKEND": _email_backend,
            "OPTIONS": {} if DEBUG else _smtp_options,
        }
    }
else:
    EMAIL_BACKEND = _email_backend
    EMAIL_HOST = _smtp_options["host"]
    EMAIL_PORT = _smtp_options["port"]
    EMAIL_HOST_USER = _smtp_options["username"]
    EMAIL_HOST_PASSWORD = _smtp_options["password"]
    EMAIL_USE_TLS = _smtp_options["use_tls"]
    EMAIL_TIMEOUT = _smtp_options["timeout"]
DEFAULT_FROM_EMAIL = os.environ.get("DJANGO_DEFAULT_FROM_EMAIL", "webmaster@localhost")
FORMS_WORKFLOWS_BASE_URL = os.environ.get(
    "FORMS_WORKFLOWS_BASE_URL",
    "http://localhost:8000" if DEBUG else "https://localhost",
)


# Login/Logout URLs
LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/forms/"
LOGOUT_REDIRECT_URL = "/"
