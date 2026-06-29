"""
Auth views — token creation, revocation, and listing.

TokenObtainView  POST  /api/v1/auth/token/
    No authentication required — this IS the auth endpoint.
    Validates email+password, creates an APIToken, returns the raw key once.

TokenRevokeView  DELETE  /api/v1/auth/token/revoke/
    Requires a valid Bearer token.
    Deactivates the token used to make the request.

TokenListView  GET  /api/v1/auth/tokens/
    Requires session or Bearer token.
    Lists all active tokens for the current user (key never shown).
"""
import logging

from django.contrib.auth import authenticate
from rest_framework.authentication import SessionAuthentication
from rest_framework.views import APIView

from apps.api.authentication import APITokenAuthentication
from apps.api.models import APIToken
from apps.api.permissions import IsAPIAuthenticated
from apps.api.response import api_error, api_list, api_success
from apps.api.scopes import ALL_SCOPES
from apps.api.serializers import APITokenSerializer, TokenCreateResponseSerializer, TokenObtainSerializer

logger = logging.getLogger('audit')


class TokenObtainView(APIView):
    """
    POST /api/v1/auth/token/

    Public endpoint — no authentication required.
    Validates credentials, creates an APIToken, and returns the raw key.
    The key is shown ONLY in this response and never again.
    """
    # Explicitly no auth/permission — this is the auth endpoint itself
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        serializer = TokenObtainSerializer(data=request.data)
        if not serializer.is_valid():
            return api_error('Invalid request data.', code='VALIDATION_ERROR', status=400)

        email = serializer.validated_data['email']
        password = serializer.validated_data['password']
        token_name = serializer.validated_data['token_name']
        requested_scopes = serializer.validated_data['scopes']

        # Authenticate user
        user = authenticate(request, email=email, password=password)
        if user is None:
            logger.warning('TOKEN_OBTAIN_FAILED email=%s ip=%s', email, _get_ip(request))
            return api_error('Invalid email or password.', code='INVALID_CREDENTIALS', status=401)

        if not user.is_active:
            return api_error('User account is disabled.', code='ACCOUNT_DISABLED', status=401)

        # Validate requested scopes
        if requested_scopes:
            invalid = [s for s in requested_scopes if s not in ALL_SCOPES]
            if invalid:
                return api_error(
                    f'Invalid scopes: {", ".join(invalid)}. Valid scopes: {", ".join(ALL_SCOPES)}',
                    code='INVALID_SCOPES',
                    status=400,
                )
            scopes = requested_scopes
        else:
            return api_error(
                'scopes are required. Pass a list of scopes to grant.',
                code='SCOPES_REQUIRED',
                status=400,
            )

        # Determine company from user (superusers have no company)
        company = getattr(user, 'company', None)

        token = APIToken.objects.create(
            user=user,
            company=company,
            name=token_name,
            scopes=scopes,
        )

        company_name = company.name if company else 'superuser'
        logger.info(
            'TOKEN_CREATED actor=%s company=%s token_id=%s scopes=%s',
            user.email, company_name, token.id, scopes,
        )

        response_data = TokenCreateResponseSerializer({
            'token': token.key,
            'token_id': token.id,
            'name': token.name,
            'scopes': token.scopes,
            'expires_at': token.expires_at,
        }).data

        return api_success(data=response_data, message='Token created successfully.', status=201)


class TokenRevokeView(APIView):
    """
    DELETE /api/v1/auth/token/revoke/

    Revokes the token used to authenticate this request.
    Sets is_active=False — the token record is preserved for audit purposes.
    """
    authentication_classes = [APITokenAuthentication]
    permission_classes = [IsAPIAuthenticated]

    def delete(self, request):
        token = request.auth
        token.is_active = False
        token.save(update_fields=['is_active', 'updated_at'])

        logger.info(
            'TOKEN_REVOKED actor=%s token_id=%s',
            request.user.email, token.id,
        )

        return api_success(message='Token revoked successfully.', status=204)


class TokenListView(APIView):
    """
    GET /api/v1/auth/tokens/

    Lists all active tokens for the current user.
    Supports both session auth (web UI) and Bearer token auth.
    The raw key is never included in this response.
    """
    authentication_classes = [APITokenAuthentication, SessionAuthentication]
    permission_classes = [IsAPIAuthenticated]

    def get(self, request):
        tokens = (
            APIToken.active_objects
            .filter(user=request.user, is_active=True)
            .order_by('-created_at')
        )
        data = APITokenSerializer(tokens, many=True).data
        return api_list(
            data=data,
            pagination={
                'total': len(data),
                'page': 1,
                'page_size': len(data),
                'total_pages': 1,
            },
        )


def _get_ip(request):
    """Extract client IP for logging."""
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded:
        return x_forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', 'unknown')
