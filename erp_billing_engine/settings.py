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
LOGOUT_REDIRECT_URL = '/login/'

AUTHENTICATION_BACKENDS = [
    'apps.accounts.backends.AuthBackend',
    'social_core.backends.google.GoogleOAuth2',
]

CRISPY_ALLOWED_TEMPLATE_PACKS = "tailwind"
CRISPY_TEMPLATE_PACK = "tailwind"

SESSION_COOKIE_AGE = 3600
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_SAVE_EVERY_REQUEST = True

# Secure cookie flags — enforced in production (DEBUG=False).
# These prevent session hijacking over HTTP and JavaScript access to cookies.
SESSION_COOKIE_HTTPONLY = True   # Prevent JS access to session cookie (Django default, explicit here)
CSRF_COOKIE_HTTPONLY = False     # Must remain False — HTMX/JS needs to read the CSRF cookie value
if not DEBUG:
    SESSION_COOKIE_SECURE = True  # Only send session cookie over HTTPS
    CSRF_COOKIE_SECURE = True     # Only send CSRF cookie over HTTPS

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
