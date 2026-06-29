"""
Company Isolation Middleware
Enforces multi-tenant data isolation at the request level.

For every authenticated, non-superuser request this middleware verifies that
the user belongs to a company.  It also attaches `request.user_company` as a
convenience so views never need to re-fetch it.

If a non-superuser somehow has no company assigned (misconfiguration or data
corruption) the request is rejected with 403 before it can reach any view,
preventing accidental cross-tenant data leakage.
"""
import logging

from django.core.exceptions import PermissionDenied
from django.urls import reverse

logger = logging.getLogger('audit')

# Paths that are always allowed regardless of company assignment
_EXEMPT_PREFIXES = (
    '/accounts/login',
    '/accounts/logout',
    '/static/',
    '/media/',
    '/favicon',
    '/api/',  # API uses token-based auth — company is set from the token, not session
)


class CompanyIsolationMiddleware:
    """
    Attaches `request.user_company` and blocks company-less non-superusers.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)

        if user and user.is_authenticated and not user.is_superuser:
            path = request.path_info

            # Skip exempt paths
            if not any(path.startswith(p) for p in _EXEMPT_PREFIXES):
                company = getattr(user, 'company', None)
                if company is None:
                    logger.warning(
                        'COMPANY_ISOLATION_BLOCK user_id=%s email=%s path=%s',
                        user.pk, user.email, path,
                    )
                    raise PermissionDenied(
                        'Your account is not associated with a company. '
                        'Please contact your administrator.'
                    )
                # Attach for convenient use in views / templates
                request.user_company = company
                # Attach branch — None means the user can access all branches
                # within their company (e.g. company admin, manager).
                request.user_branch = getattr(user, 'branch', None)
        elif user and user.is_superuser:
            request.user_company = None  # superuser sees all
            request.user_branch = None   # superuser sees all branches

        return self.get_response(request)
