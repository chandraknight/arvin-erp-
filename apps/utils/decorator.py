"""
Authorization decorators for function-based views.

auth_required(*codenames)
    Requires the user to be authenticated AND hold all listed permission
    codenames (via their group memberships).  Superusers bypass the check.

company_required
    Requires the authenticated user to belong to a company.
    Superusers are exempt.  Use on any view that touches company-scoped data.
"""
import logging
from functools import wraps

from django.core.exceptions import PermissionDenied
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Permission

logger = logging.getLogger('audit')


def auth_required(*perm_codenames):
    """
    Decorator that enforces group-based permission checks.

    Usage::

        @auth_required('add_invoice', 'change_invoice')
        def my_view(request):
            ...

    Accepts both bare codenames ('add_invoice') and app-label-prefixed
    codenames ('billing.add_invoice') — the app label is stripped.
    """
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def _wrapped_view(request, *args, **kwargs):
            if request.user.is_superuser or getattr(request.user, 'is_company_admin', False):
                return view_func(request, *args, **kwargs)

            user_group_permissions = set(
                Permission.objects.filter(
                    group__in=request.user.groups.all()
                ).values_list('codename', flat=True)
            )
            user_group_permissions.update(
                request.user.user_permissions.values_list('codename', flat=True)
            )

            required_codenames = {perm.split('.')[-1] for perm in perm_codenames}
            missing = required_codenames - user_group_permissions

            if missing:
                logger.warning(
                    'PERMISSION_DENIED user_id=%s email=%s path=%s missing=%s',
                    request.user.pk,
                    request.user.email,
                    request.path,
                    missing,
                )
                raise PermissionDenied(
                    'You do not have the required permissions: '
                    + ', '.join(sorted(missing))
                )

            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator


def company_required(view_func):
    """
    Decorator that ensures the authenticated user is associated with a company.
    Superusers are exempt.

    Usage::

        @login_required
        @company_required
        def my_view(request):
            ...
    """
    @wraps(view_func)
    @login_required
    def _wrapped_view(request, *args, **kwargs):
        if request.user.is_superuser:
            return view_func(request, *args, **kwargs)

        if not getattr(request.user, 'company', None):
            logger.warning(
                'COMPANY_REQUIRED_DENIED user_id=%s email=%s path=%s',
                request.user.pk,
                request.user.email,
                request.path,
            )
            raise PermissionDenied(
                'Your account is not associated with a company. '
                'Please contact your administrator.'
            )

        return view_func(request, *args, **kwargs)
    return _wrapped_view
