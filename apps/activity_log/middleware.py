"""
Middleware that stores the current request (user + IP) in a thread-local
so signals can access it without being passed the request explicitly.
"""
import threading

_thread_locals = threading.local()


def get_current_user():
    return getattr(_thread_locals, 'user', None)


def get_current_ip():
    return getattr(_thread_locals, 'ip_address', None)


class ActivityLogMiddleware:
    """
    Stores the authenticated user and client IP in thread-local storage
    for the duration of each request so signals can read them.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _thread_locals.user = getattr(request, 'user', None)
        _thread_locals.ip_address = self._get_ip(request)
        response = self.get_response(request)
        # Clean up to avoid leaking between requests in the same thread
        _thread_locals.user = None
        _thread_locals.ip_address = None
        return response

    @staticmethod
    def _get_ip(request):
        x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded:
            return x_forwarded.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')
