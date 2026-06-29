"""
Login Attempt Guard Middleware
Tracks failed login attempts per IP and per email address.
Temporarily blocks an IP or account after too many consecutive failures,
preventing brute-force credential attacks.

Thresholds (overridable via settings):
  LOGIN_ATTEMPT_MAX_FAILURES  — default 5
  LOGIN_ATTEMPT_LOCKOUT_SECS  — default 300 (5 minutes)
"""
import time
import threading
import logging
from collections import defaultdict

from django.conf import settings
from django.contrib.auth.signals import user_login_failed, user_logged_in
from django.dispatch import receiver
from django.http import HttpResponse

from apps.utils.ip import get_client_ip

logger = logging.getLogger('audit')

_MAX_FAILURES: int = getattr(settings, 'LOGIN_ATTEMPT_MAX_FAILURES', 5)
_LOCKOUT_SECS: int = getattr(settings, 'LOGIN_ATTEMPT_LOCKOUT_SECS', 300)

# {key: {'count': int, 'locked_until': float}}
_attempts: dict = defaultdict(lambda: {'count': 0, 'locked_until': 0.0})
_lock = threading.Lock()


def _get_ip(request) -> str:
    return get_client_ip(request)


def _record_failure(key: str):
    now = time.monotonic()
    with _lock:
        entry = _attempts[key]
        # Reset counter if previous lockout has expired
        if entry['locked_until'] and now > entry['locked_until']:
            entry['count'] = 0
            entry['locked_until'] = 0.0
        entry['count'] += 1
        if entry['count'] >= _MAX_FAILURES:
            entry['locked_until'] = now + _LOCKOUT_SECS
            logger.warning(
                'LOGIN_LOCKOUT key=%s failures=%d locked_for=%ds',
                key, entry['count'], _LOCKOUT_SECS,
            )


def _is_locked(key: str) -> bool:
    now = time.monotonic()
    with _lock:
        entry = _attempts[key]
        if entry['locked_until'] and now < entry['locked_until']:
            return True
        return False


def _clear(key: str):
    with _lock:
        _attempts.pop(key, None)


# ── Django auth signals ────────────────────────────────────────────────────────

@receiver(user_login_failed)
def on_login_failed(sender, credentials, request, **kwargs):
    if request is None:
        return
    ip = _get_ip(request)
    email = (credentials or {}).get('email', '')
    _record_failure(f'ip:{ip}')
    if email:
        _record_failure(f'email:{email}')


@receiver(user_logged_in)
def on_login_success(sender, user, request, **kwargs):
    if request is None:
        return
    ip = _get_ip(request)
    _clear(f'ip:{ip}')
    if user and user.email:
        _clear(f'email:{user.email}')


# ── Middleware ─────────────────────────────────────────────────────────────────

class LoginAttemptGuardMiddleware:
    """
    Intercepts requests to the login endpoint and returns HTTP 429 if the
    originating IP or the submitted email is currently locked out.
    """

    LOGIN_PATH = '/accounts/login'

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method == 'POST' and request.path_info.startswith(self.LOGIN_PATH):
            ip = _get_ip(request)
            email = request.POST.get('email', '')

            if _is_locked(f'ip:{ip}'):
                logger.warning('LOGIN_BLOCKED ip=%s', ip)
                return self._locked_response()

            if email and _is_locked(f'email:{email}'):
                logger.warning('LOGIN_BLOCKED email=%s ip=%s', email, ip)
                return self._locked_response()

        return self.get_response(request)

    @staticmethod
    def _locked_response() -> HttpResponse:
        return HttpResponse(
            f'Account temporarily locked due to too many failed login attempts. '
            f'Please try again in {_LOCKOUT_SECS // 60} minutes.',
            status=429,
            content_type='text/plain',
        )
