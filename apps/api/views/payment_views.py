"""
Payment views.

PaymentListView    GET  /api/v1/payments/
PaymentDetailView  GET  /api/v1/payments/<uuid:pk>/

All views use request.auth.company for tenant isolation.
"""
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView

from apps.api.authentication import APITokenAuthentication
from apps.api.pagination import paginate_queryset
from apps.api.permissions import HasAPIScope
from apps.api.response import api_error, api_list, api_success
from apps.api.scopes import SCOPE_PAYMENTS_READ
from apps.api.serializers import PaymentSerializer
from apps.payments.models import Payment


class PaymentListView(APIView):
    """
    GET /api/v1/payments/

    Returns a paginated list of payments for the token's company.
    Query params:
        ?from_date=YYYY-MM-DD
        ?to_date=YYYY-MM-DD
        ?payment_type=CUSTOMER|VENDOR|EXPENSE|SALARY|OTHER
        ?page=<int>
        ?page_size=<int>  (max 100)
    """
    authentication_classes = [APITokenAuthentication]
    permission_classes = [HasAPIScope]
    required_scope = SCOPE_PAYMENTS_READ

    def get(self, request):
        company = request.auth.company
        if company is None:
            return api_error('Superuser tokens must specify a company.', code='NO_COMPANY', status=400)

        qs = (
            Payment.active_objects
            .filter(company=company)
            .select_related('invoice')
            .order_by('-date', '-created_at')
        )

        from_date = request.GET.get('from_date', '').strip()
        if from_date:
            qs = qs.filter(date__gte=from_date)

        to_date = request.GET.get('to_date', '').strip()
        if to_date:
            qs = qs.filter(date__lte=to_date)

        payment_type = request.GET.get('payment_type', '').strip().upper()
        if payment_type:
            qs = qs.filter(payment_type=payment_type)

        page_data, total, total_pages, page = paginate_queryset(qs, request)
        page_size = int(request.GET.get('page_size', 20))

        data = PaymentSerializer(page_data, many=True).data
        return api_list(
            data=data,
            pagination={
                'total': total,
                'page': page,
                'page_size': min(page_size, 100),
                'total_pages': total_pages,
            },
        )


class PaymentDetailView(APIView):
    """
    GET /api/v1/payments/<uuid:pk>/

    Returns a single payment.
    Ownership is verified against the token's company.
    """
    authentication_classes = [APITokenAuthentication]
    permission_classes = [HasAPIScope]
    required_scope = SCOPE_PAYMENTS_READ

    def get(self, request, pk):
        company = request.auth.company
        if company is None:
            return api_error('Superuser tokens must specify a company.', code='NO_COMPANY', status=400)

        payment = get_object_or_404(
            Payment.active_objects.select_related('invoice'),
            pk=pk,
            company=company,
        )
        data = PaymentSerializer(payment).data
        return api_success(data=data)
