"""
Audit Log Middleware
Persists a structured audit trail for every mutating HTTP request (POST/PUT/PATCH/DELETE).
Records: who, what, when, from where, and the outcome.

The log is written to the Django 'audit' logger which can be routed to a
dedicated file, database handler, or external SIEM via logging config.
"""
import json
import logging
import time

from apps.utils.ip import get_client_ip

logger = logging.getLogger('audit')


class AuditLogMiddleware:
    """
    Logs all state-changing requests with user identity, IP, path, method,
    HTTP status, and response time.  Read-only GET/HEAD requests are skipped
    to keep the audit log focused on mutations.
    """

    MUTATING_METHODS = frozenset({'POST', 'PUT', 'PATCH', 'DELETE'})

    # Paths that carry credentials — never log their POST body
    SENSITIVE_PATHS = frozenset({
        '/accounts/login',
        '/accounts/password',
        '/api/auth',
    })

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method not in self.MUTATING_METHODS:
            return self.get_response(request)

        start = time.monotonic()
        response = self.get_response(request)
        elapsed_ms = round((time.monotonic() - start) * 1000, 1)

        self._write_log(request, response, elapsed_ms)
        return response

    def _write_log(self, request, response, elapsed_ms: float):
        user = getattr(request, 'user', None)
        user_id = user.pk if user and user.is_authenticated else None
        user_email = user.email if user and user.is_authenticated else 'anonymous'

        ip = self._get_ip(request)
        path = request.path_info
        is_sensitive = any(path.startswith(s) for s in self.SENSITIVE_PATHS)

        entry = {
            'event': 'http_mutation',
            'method': request.method,
            'path': path,
            'user_id': user_id,
            'user_email': user_email,
            'ip': ip,
            'status': response.status_code,
            'elapsed_ms': elapsed_ms,
            'user_agent': request.META.get('HTTP_USER_AGENT', '')[:200],
        }

        # Attach POST data for non-sensitive paths (strip passwords just in case)
        if not is_sensitive and request.method == 'POST':
            try:
                post_data = dict(request.POST)
                post_data.pop('password', None)
                post_data.pop('password1', None)
                post_data.pop('password2', None)
                post_data.pop('csrfmiddlewaretoken', None)
                entry['post_data'] = post_data
            except Exception:
                pass

        level = logging.WARNING if response.status_code >= 400 else logging.INFO
        logger.log(level, json.dumps(entry, default=str))

    @staticmethod
    def _get_ip(request) -> str:
        return get_client_ip(request)
