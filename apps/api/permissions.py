"""
DRF permission classes for the API app.

HasAPIScope  — requires a specific scope string on the token.
IsAPIAuthenticated — requires any valid API token (no scope check).
"""
from rest_framework.permissions import BasePermission


class IsAPIAuthenticated(BasePermission):
    """
    Grants access to any request that has been authenticated via APITokenAuthentication.
    Checks that request.user is authenticated and request.auth is an APIToken instance.
    """

    message = 'Authentication via API token is required.'

    def has_permission(self, request, view):
        from apps.api.models import APIToken

        return (
            request.user is not None
            and request.user.is_authenticated
            and isinstance(request.auth, APIToken)
        )


class HasAPIScope(BasePermission):
    """
    Grants access only when the token carries the required scope.

    Usage in a view:
        class MyView(APIView):
            permission_classes = [HasAPIScope]
            required_scope = 'invoices:read'

    Superusers bypass the scope check but still need a valid token.
    """

    message = 'Your token does not have the required scope for this action.'

    # Subclasses or view instances set this
    required_scope = None

    def has_permission(self, request, view):
        from apps.api.models import APIToken

        # Must have a valid API token
        if not (
            request.user is not None
            and request.user.is_authenticated
            and isinstance(request.auth, APIToken)
        ):
            return False

        # Superusers bypass scope check
        if request.user.is_superuser:
            return True

        # Get required_scope from the view (allows per-view override)
        scope = getattr(view, 'required_scope', self.required_scope)
        if scope is None:
            # No scope required — just need a valid token
            return True

        return scope in request.auth.scopes
