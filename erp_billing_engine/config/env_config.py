# config/env_config.py
from pathlib import Path
import os
import environ


# Initialize environ
env = environ.Env()

# Path to the .env file
env.read_env(os.path.join(Path(__file__).resolve().parent.parent.parent, '.env'))


DEPLOY_TAG_PATH = env('DEPLOY_TAG_PATH', default='/home/snsstagi/erp-api/deploy.log')

ADMIN_ENABLE = env('ADMIN_ENABLE', default=False)

SECRET_KEY = env('SECRET_KEY')

DEBUG = env('DEBUG', cast=bool, default=False)

ALLOWED_HOSTS = env.list('ALLOWED_HOSTS')

CSRF_TRUSTED_ORIGINS = env.list('CSRF_TRUSTED_ORIGINS')

# Persistent DB connections — reuse across requests instead of opening a new
# connection per request. 60s is safe for gunicorn with sync workers.
# Set CONN_MAX_AGE=0 in .env to disable (e.g. for PgBouncer transaction-mode).
_CONN_MAX_AGE = env.int('CONN_MAX_AGE', default=60)

# Data base config postgres
if env('DATABASE_URL', default=None):
    DATABASES = {
        'default': {**env.db('DATABASE_URL'), 'CONN_MAX_AGE': _CONN_MAX_AGE}
    }
    # Use django_cockroachdb engine for CockroachDB
    if 'cockroachlabs.cloud' in DATABASES['default'].get('HOST', ''):
        DATABASES['default']['ENGINE'] = 'django_cockroachdb'
else:
    DATABASES = {
        'default': {
            'ENGINE': env('DB_ENGINE', default='django.db.backends.postgresql'),
            'NAME': env('DB_NAME', default='erp'),
            'USER': env('DB_USER'),
            'PASSWORD': env('DB_PASSWORD'),
            'HOST': env('DB_HOST', default='localhost'),
            'PORT': env('DB_PORT', default='5432'),
            'CONN_MAX_AGE': _CONN_MAX_AGE,
        }
    }

# Cache — defaults to LocMemCache (dev-safe, in-process).
# Set REDIS_URL=redis://localhost:6379/1 in .env to enable Redis (recommended in prod).
_redis_url = env('REDIS_URL', default=None)
if _redis_url:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': _redis_url,
        }
    }
else:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'erp-cache',
        }
    }

INTERNAL_IPS = env.list('INTERNAL_IPS')

# Time Zone
TIME_ZONE=env('TIME_ZONE', default="UTC")
LANGUAGE_CODE=env('LANGUAGE_CODE', default="en-us")

# Dic
STATIC_ROOT = env('STATIC_ROOT', default="static/")

MEDIA_ROOT = env('MEDIA_ROOT', default=None)

LOGS_DIR = env('LOGS_DIR',default="logs/")

# API token default expiry in days (0 = never expires)
API_TOKEN_EXPIRY_DAYS = env.int('API_TOKEN_EXPIRY_DAYS', default=0)

# ── Email / SMTP ──────────────────────────────────────────────────────────────
# In production set EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
# and fill in SMTP_* vars. Defaults to console backend (safe in dev).
EMAIL_BACKEND = env(
    'EMAIL_BACKEND',
    default='django.core.mail.backends.console.EmailBackend',
)
EMAIL_HOST         = env('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT         = env.int('EMAIL_PORT', default=587)
EMAIL_HOST_USER    = env('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD', default='')
EMAIL_USE_TLS      = env.bool('EMAIL_USE_TLS', default=True)
EMAIL_USE_SSL      = env.bool('EMAIL_USE_SSL', default=False)
DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', default='noreply@yourcompany.com')
SERVER_EMAIL       = env('SERVER_EMAIL', default='noreply@yourcompany.com')

# ── Google OAuth2 ─────────────────────────────────────────────────────────────
SOCIAL_AUTH_GOOGLE_OAUTH2_KEY    = env('GOOGLE_CLIENT_ID', default='')
SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET = env('GOOGLE_CLIENT_SECRET', default='')
SOCIAL_AUTH_GOOGLE_OAUTH2_SCOPE  = ['email', 'profile']
SOCIAL_AUTH_URL_NAMESPACE        = 'social'
SOCIAL_AUTH_LOGIN_REDIRECT_URL   = '/store/account/'
SOCIAL_AUTH_NEW_USER_REDIRECT_URL = '/store/account/'
SOCIAL_AUTH_LOGIN_ERROR_URL      = '/store/login/'
SOCIAL_AUTH_PIPELINE = (
    'social_core.pipeline.social_auth.social_details',
    'social_core.pipeline.social_auth.social_uid',
    'social_core.pipeline.social_auth.auth_allowed',
    'social_core.pipeline.social_auth.social_user',
    'social_core.pipeline.user.get_username',
    'social_core.pipeline.user.create_user',
    'social_core.pipeline.social_auth.associate_user',
    'social_core.pipeline.social_auth.load_extra_data',
    'social_core.pipeline.user.user_details',
    'apps.ecom.pipeline.block_staff_social_login',
)

# ── reCAPTCHA v3 ──────────────────────────────────────────────────────────────
RECAPTCHA_SITE_KEY   = env('RECAPTCHA_SITE_KEY', default='')
RECAPTCHA_SECRET_KEY = env('RECAPTCHA_SECRET_KEY', default='')