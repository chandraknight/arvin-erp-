"""
Security Headers Middleware
Adds HTTP security headers to every response to protect against common
web vulnerabilities: XSS, clickjacking, MIME sniffing, and information leakage.
"""
from django.conf import settings


class SecurityHeadersMiddleware:
    """
    Injects security-related HTTP response headers on every response.
    These headers are enforced at the browser level and cannot be bypassed
    by application-layer bugs.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        self._apply_headers(response)
        return response

    def _apply_headers(self, response):
        # Prevent browsers from MIME-sniffing the content type
        response['X-Content-Type-Options'] = 'nosniff'

        # Deny all framing (stronger than SAMEORIGIN for this ERP)
        response['X-Frame-Options'] = 'DENY'

        # Enable XSS filter in older browsers
        response['X-XSS-Protection'] = '1; mode=block'

        # Only send referrer on same-origin requests
        response['Referrer-Policy'] = 'strict-origin-when-cross-origin'

        # Restrict browser features not needed by this app
        response['Permissions-Policy'] = (
            'geolocation=(), microphone=(), camera=(), '
            'payment=(), usb=(), magnetometer=(), gyroscope=()'
        )

        # Content Security Policy
        # style-src / font-src / script-src must include every CDN used in base.html:
        #   cdn.jsdelivr.net   — Tailwind CSS, flatpickr CSS/JS
        #   cdnjs.cloudflare.com — Font Awesome CSS
        #   fonts.cdnfonts.com — Ogirema web font (CSS + woff2)
        #   code.jquery.com    — jQuery
        #   unpkg.com          — Alpine.js, HTMX
        # img-src must include:
        #   plus.unsplash.com  — login page illustration
        #   upload.wikimedia.org — 500 error page SVGs
        #   data:              — base64 inline logo on login page
        CDN_STYLE  = "cdn.jsdelivr.net cdnjs.cloudflare.com fonts.cdnfonts.com cdn.quilljs.com fonts.bunny.net fonts.googleapis.com"
        CDN_FONT   = "cdn.jsdelivr.net cdnjs.cloudflare.com fonts.cdnfonts.com fonts.bunny.net fonts.gstatic.com data:"
        CDN_SCRIPT = "cdn.jsdelivr.net cdnjs.cloudflare.com code.jquery.com unpkg.com cdn.quilljs.com"
        CDN_IMG    = "plus.unsplash.com upload.wikimedia.org data:"

        if not settings.DEBUG:
            response['Content-Security-Policy'] = (
                "default-src 'self'; "
                f"script-src 'self' 'unsafe-inline' 'unsafe-eval' blob: {CDN_SCRIPT}; "
                f"style-src 'self' 'unsafe-inline' {CDN_STYLE}; "
                f"img-src 'self' {CDN_IMG}; "
                f"font-src 'self' {CDN_FONT}; "
                f"connect-src 'self'; "
                "frame-ancestors 'none';"
            )
        else:
            # Relaxed CSP for development (allows inline scripts, debug toolbar, etc.)
            response['Content-Security-Policy'] = (
                "default-src 'self'; "
                f"script-src 'self' 'unsafe-inline' 'unsafe-eval' {CDN_SCRIPT}; "
                f"style-src 'self' 'unsafe-inline' {CDN_STYLE}; "
                f"img-src 'self' {CDN_IMG}; "
                f"font-src 'self' {CDN_FONT}; "
                "connect-src 'self';"
            )

        # HSTS — only in production (requires HTTPS)
        if not settings.DEBUG:
            response['Strict-Transport-Security'] = (
                'max-age=31536000; includeSubDomains'
            )

        # Remove server fingerprinting headers if present
        for header in ('Server', 'X-Powered-By'):
            try:
                del response[header]
            except KeyError:
                pass

        return response
