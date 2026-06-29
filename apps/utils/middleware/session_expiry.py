from django.shortcuts import redirect
from django.urls import reverse
from django.utils.deprecation import MiddlewareMixin


class SessionExpiryMiddleware(MiddlewareMixin):
    def process_request(self, request):
        # API paths use token-based auth — session expiry does not apply
        if request.path_info.startswith('/api/'):
            return None

        exempt_urls = [
            reverse('accounts:login'),
            reverse('accounts:logout'),
        ]

        if (request.user.is_authenticated and
                not request.session.get('_session_is_active', False) and
                request.path not in exempt_urls):
            request.session.flush()
            return redirect(f"{reverse('accounts:login')}?session_expired=1")

        return None

    def process_response(self, request, response):
        if request.user.is_authenticated:
            request.session['_session_is_active'] = True
        return response