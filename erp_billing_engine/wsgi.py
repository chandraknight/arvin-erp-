import os

os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
os.environ.setdefault('OMP_NUM_THREADS', '1')

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'erp_billing_engine.settings')

_application = get_wsgi_application()


def application(environ, start_response):
    # cPanel's Apache terminates SSL and sets HTTPS=on in the WSGI environ
    # but does NOT set HTTP_X_FORWARDED_PROTO. Without this patch Django's
    # request.is_secure() returns False, which causes SESSION_COOKIE_SECURE
    # and CSRF_COOKIE_SECURE cookies to be issued with Secure flag but the
    # redirect after login goes to http://, so the browser never sends them.
    if environ.get('HTTPS', 'off') == 'on':
        environ['wsgi.url_scheme'] = 'https'
    return _application(environ, start_response)
