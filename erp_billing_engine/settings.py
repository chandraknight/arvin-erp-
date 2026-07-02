from pathlib import Path
from .config.config import *

BASE_DIR = Path(__file__).resolve().parent.parent

LOGS_DIR = os.path.join(BASE_DIR, 'logs')
os.makedirs(LOGS_DIR, exist_ok=True)

ADMIN_ENABLE = ADMIN_ENABLE
SECRET_KEY = SECRET_KEY
DEBUG = DEBUG

ALLOWED_HOSTS = ALLOWED_HOSTS

CSRF_TRUSTED_ORIGINS = CSRF_TRUSTED_ORIGINS

# Application definition
INSTALLED_APPS = INSTALLED_APPS

MIDDLEWARE = MIDDLEWARE

ROOT_URLCONF = 'erp_billing_engine.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'social_django.context_processors.backends',
                'social_django.context_processors.login_redirect',
            ],
            "builtins": [
                "django_cotton.templatetags.cotton",
                "django.contrib.humanize.templatetags.humanize",
                "widget_tweaks.templatetags.widget_tweaks",
            ],
        }
    }
]

# Database Configurations
DATABASES = DATABASES

WSGI_APPLICATION = 'erp_billing_engine.wsgi.application'

# Password validation

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
    "django.contrib.auth.hashers.ScryptPasswordHasher",
]

# Internationalization

LANGUAGE_CODE = LANGUAGE_CODE

TIME_ZONE = TIME_ZONE

USE_I18N = True

USE_TZ = True

# Static files (CSS, JavaScript, Images)

MEDIA_URL = '/media/'
MEDIA_ROOT = MEDIA_ROOT if MEDIA_ROOT else os.path.join(BASE_DIR, 'media')

STATIC_URL = '/static/'

STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'static'),
]

STATICFILES_STORAGE = 'whitenoise.storage.CompressedStaticFilesStorage'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/accounts/dashboard/'
LOGOUT_REDIRECT_URL = '/accounts/login/'

AUTHENTICATION_BACKENDS = [
    'apps.accounts.backends.AuthBackend',
    'social_core.backends.google.GoogleOAuth2',
]

CRISPY_ALLOWED_TEMPLATE_PACKS = "tailwind"
CRISPY_TEMPLATE_PACK = "tailwind"

SESSION_COOKIE_AGE = 3600
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_SAVE_EVERY_REQUEST = True
SESSION_COOKIE_NAME = 'erpSessionId'  # renamed to invalidate stale cookies from old SECRET_KEY

# Secure cookie flags — enforced in production (DEBUG=False).
# These prevent session hijacking over HTTP and JavaScript access to cookies.
SESSION_COOKIE_HTTPONLY = True   # Prevent JS access to session cookie (Django default, explicit here)
CSRF_COOKIE_HTTPONLY = False     # Must remain False — HTMX/JS needs to read the CSRF cookie value
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'
if not DEBUG:
    # cPanel Apache terminates SSL. It sets both HTTPS=on (handled in wsgi.py)
    # AND HTTP_X_FORWARDED_PROTO=https in most configurations.
    # SECURE_PROXY_SSL_HEADER makes Django trust the forwarded proto header so
    # request.is_secure() returns True, which ensures:
    #   1. The post-login redirect goes to https:// not http://
    #   2. SESSION_COOKIE_SECURE cookies are sent by the browser on follow-up requests
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    USE_X_FORWARDED_HOST = True
    # SECURE_COOKIES can be set to False in .env as a diagnostic fallback if
    # Apache does not forward X-Forwarded-Proto correctly and the Secure cookie
    # flag is causing the post-login redirect loop.
    SESSION_COOKIE_SECURE = SECURE_COOKIES
    CSRF_COOKIE_SECURE = SECURE_COOKIES

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ]
}

INTERNAL_IPS = INTERNAL_IPS


AUTH_USER_MODEL= 'accounts.User'
