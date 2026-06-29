"""
Company views.

CompanyDetailView  GET  /api/v1/company/
    Returns the company associated with the token.
    Superusers without a company get 404.
"""
from rest_framework.views import APIView

from apps.api.authentication import APITokenAuthentication
from apps.api.permissions import HasAPIScope
from apps.api.response import api_error, api_success
from apps.api.serializers import CompanySerializer


class CompanyDetailView(APIView):
    """
    GET /api/v1/company/

    Returns the company scoped to the token.
    No specific scope required — any valid token can read its own company.
    """
    authentication_classes = [APITokenAuthentication]
    permission_classes = [HasAPIScope]
    required_scope = None  # Any authenticated token can access

    def get(self, request):
        company = request.auth.company
        if company is None:
            return api_error(
                'No company associated with this token.',
                code='NO_COMPANY',
                status=404,
            )
        data = CompanySerializer(company).data
        return api_success(data=data)
