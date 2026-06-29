"""
Rate Limiting Middleware
Protects sensitive endpoints from brute-force and DoS using Django's cache
backend. Works correctly with multiple gunicorn workers and Redis.

Configure limits via settings.RATE_LIMIT_RULES:
  [(path_prefix, max_requests, window_seconds, label), ...]
"""
from django.core.cache import cache
from django.http import HttpResponse
from django.conf import settings

from apps.utils.ip import get_client_ip


# (path_prefix, max_requests, window_seconds, label)
_DEFAULT_RULES = [
    ('/accounts/login',   10,  60,  'login'),
    ('/accounts/logout',  30,  60,  'logout'),
    ('/api/',             200, 60,  'api'),
]


def _is_rate_limited(key: str, max_requests: int, window_seconds: int) -> bool:
    """
    Fixed-window rate limiter backed by Django's cache.
    Works with LocMemCache (dev), Redis, and Memcached (prod).
    """
    count = cache.get(key, 0)
    if count >= max_requests:
        return True
    if count == 0:
        cache.set(key, 1, window_seconds)
    else:
        try:
            cache.incr(key)
        except ValueError:
            cache.set(key, 1, window_seconds)
    return False


class RateLimitMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.rules = getattr(settings, 'RATE_LIMIT_RULES', _DEFAULT_RULES)

    def __call__(self, request):
        path = request.path_info
        ip = get_client_ip(request)

        for prefix, max_req, window, label in self.rules:
            if path.startswith(prefix):
                key = f'rl:{label}:{ip}'
                if _is_rate_limited(key, max_req, window):
                    return self._too_many_requests(window)

        return self.get_response(request)

    @staticmethod
    def _too_many_requests(window: int) -> HttpResponse:
        response = HttpResponse(
            f'Too many requests. Please wait {window} seconds before retrying.',
            status=429,
            content_type='text/plain',
        )
        response['Retry-After'] = str(window)
        return response
