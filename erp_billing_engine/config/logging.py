import os

# LOGS_DIR is defined in settings.py after BASE_DIR is resolved.
# We reference it via a lazy lambda so this file can be imported early.

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,

    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
        'audit': {
            # Structured one-line format for easy parsing / SIEM ingestion
            'format': '{asctime} AUDIT {levelname} {message}',
            'style': '{',
        },
    },

    'handlers': {
        # General application errors → logs/app.log
        'app_file': {
            'level': 'WARNING',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': 'logs/app.log',
            'maxBytes': 1024 * 1024 * 10,   # 10 MB
            'backupCount': 10,
            'formatter': 'verbose',
        },

        # Security / audit trail → logs/audit.log  (never rotated away carelessly)
        'audit_file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': 'logs/audit.log',
            'maxBytes': 1024 * 1024 * 20,   # 20 MB
            'backupCount': 30,              # keep 30 × 20 MB = 600 MB of history
            'formatter': 'audit',
        },

        # Console output (useful in development and container stdout)
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
    },

    'loggers': {
        # Dedicated audit logger used by security middleware & decorators
        'audit': {
            'handlers': ['audit_file', 'console'],
            'level': 'INFO',
            'propagate': False,
        },

        # Django internals
        'django': {
            'handlers': ['app_file', 'console'],
            'level': 'WARNING',
            'propagate': False,
        },

        # Catch-all for the project's own apps
        'apps': {
            'handlers': ['app_file', 'console'],
            'level': 'WARNING',
            'propagate': False,
        },
    },
}
