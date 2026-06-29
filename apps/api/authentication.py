"""
Custom DRF authentication class for Bearer token auth.

Usage:
    Authorization: Bearer <64-char-hex-token>

On success returns (user, token) where token is the APIToken instance.
request.auth is the APIToken — views use request.auth.company for tenant isolation.
"""
import hmac
import logging

from django.utils import timezone
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

logger = logging.getLogger(__name__)


class APITokenAuthentication(BaseAuthentication):
    """
    Authenticates requests using a Bearer token stored in the APIToken model.

    DRF convention: returns (user, auth) where auth is the APIToken instance.
    Views access the token via request.auth.
    """

    keyword = 'Bearer'

    def authenticate(self, request):
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')

        if not auth_header:
            # No Authorization header — let other authenticators try
            return None

        parts = auth_header.split()

        if len(parts) == 1:
            raise AuthenticationFailed('Invalid token header. No token provided.')

        if len(parts) > 2:
            raise AuthenticationFailed('Invalid token header. Token string should not contain spaces.')

        if parts[0].lower() != self.keyword.lower():
            # Not a Bearer token — let other authenticators try
            return None

        raw_token = parts[1]
        return self._authenticate_token(raw_token)

    def _authenticate_token(self, raw_token):
        from apps.api.models import APIToken

        try:
            token = (
                APIToken.objects
                .select_related('user', 'company')
                .get(key=raw_token, is_active=True)
            )
        except APIToken.DoesNotExist:
            raise AuthenticationFailed('Invalid or inactive token.')

        # Constant-time comparison to prevent timing oracle attacks
        if not hmac.compare_digest(token.key, raw_token):
            raise AuthenticationFailed('Invalid or inactive token.')

        # Check expiry
        if token.expires_at is not None and token.expires_at < timezone.now():
            raise AuthenticationFailed('Token has expired.')

        # Update last_used_at without triggering signals (use update())
        APIToken.objects.filter(pk=token.pk).update(last_used_at=timezone.now())

        user = token.user
        if not user.is_active:
            raise AuthenticationFailed('User account is disabled.')

        return (user, token)

    def authenticate_header(self, request):
        return self.keyword
