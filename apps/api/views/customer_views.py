"""
Customer views.

CustomerListView    GET   /api/v1/customers/
CustomerDetailView  GET   /api/v1/customers/<uuid:pk>/
CustomerCreateView  POST  /api/v1/customers/create/

All views use request.auth.company for tenant isolation.
"""
import logging

from django.shortcuts import get_object_or_404
from rest_framework.views import APIView

from apps.api.authentication import APITokenAuthentication
from apps.api.pagination import paginate_queryset
from apps.api.permissions import HasAPIScope
from apps.api.response import api_error, api_list, api_success
from apps.api.scopes import SCOPE_CUSTOMERS_READ, SCOPE_CUSTOMERS_WRITE
from apps.api.serializers import CustomerCreateSerializer, CustomerSerializer
from apps.customers.models import Customer

logger = logging.getLogger(__name__)


class CustomerListView(APIView):
    """
    GET /api/v1/customers/

    Returns a paginated list of customers for the token's company.
    Query params:
        ?search=<name_or_email>
        ?page=<int>
        ?page_size=<int>  (max 100)
    """
    authentication_classes = [APITokenAuthentication]
    permission_classes = [HasAPIScope]
    required_scope = SCOPE_CUSTOMERS_READ

    def get(self, request):
        company = request.auth.company
        if company is None:
            return api_error('Superuser tokens must specify a company.', code='NO_COMPANY', status=400)

        qs = Customer.active_objects.filter(company=company).order_by('name')

        search = request.GET.get('search', '').strip()
        if search:
            qs = qs.filter(name__icontains=search) | Customer.active_objects.filter(
                company=company, email__icontains=search
            )
            qs = qs.distinct()

        page_data, total, total_pages, page = paginate_queryset(qs, request)
        page_size = int(request.GET.get('page_size', 20))

        data = CustomerSerializer(page_data, many=True).data
        return api_list(
            data=data,
            pagination={
                'total': total,
                'page': page,
                'page_size': min(page_size, 100),
                'total_pages': total_pages,
            },
        )


class CustomerDetailView(APIView):
    """
    GET /api/v1/customers/<uuid:pk>/

    Returns a single customer. Ownership is verified against the token's company.
    """
    authentication_classes = [APITokenAuthentication]
    permission_classes = [HasAPIScope]
    required_scope = SCOPE_CUSTOMERS_READ

    def get(self, request, pk):
        company = request.auth.company
        if company is None:
            return api_error('Superuser tokens must specify a company.', code='NO_COMPANY', status=400)

        customer = get_object_or_404(Customer.active_objects, pk=pk, company=company)
        data = CustomerSerializer(customer).data
        return api_success(data=data)


class CustomerCreateView(APIView):
    """
    POST /api/v1/customers/create/

    Creates a new customer scoped to the token's company.
    """
    authentication_classes = [APITokenAuthentication]
    permission_classes = [HasAPIScope]
    required_scope = SCOPE_CUSTOMERS_WRITE

    def post(self, request):
        company = request.auth.company
        if company is None:
            return api_error('Superuser tokens must specify a company.', code='NO_COMPANY', status=400)

        serializer = CustomerCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return api_error(
                str(serializer.errors),
                code='VALIDATION_ERROR',
                status=400,
            )

        customer = serializer.save(
            company=company,
            created_by=request.user,
        )

        data = CustomerSerializer(customer).data
        return api_success(data=data, message='Customer created successfully.', status=201)
