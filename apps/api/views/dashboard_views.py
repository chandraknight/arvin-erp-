"""
Dashboard view.

DashboardView  GET  /api/v1/dashboard/

Returns summary metrics for the token's company.
"""
from datetime import date
from decimal import Decimal

from django.db.models import Sum
from rest_framework.views import APIView

from apps.api.authentication import APITokenAuthentication
from apps.api.permissions import HasAPIScope
from apps.api.response import api_error, api_success
from apps.api.scopes import SCOPE_DASHBOARD_READ
from apps.api.serializers import DashboardSerializer
from apps.billing.models import Invoice
from apps.customers.models import Customer
from apps.payments.models import Payment


class DashboardView(APIView):
    """
    GET /api/v1/dashboard/

    Returns:
        total_invoices      — count of all non-deleted invoices
        total_customers     — count of all active customers
        total_outstanding   — sum of outstanding_balance across all invoices
        today_sales         — sum of totals for invoices with today's transaction_date
        recent_invoices     — last 5 invoices (newest first)
    """
    authentication_classes = [APITokenAuthentication]
    permission_classes = [HasAPIScope]
    required_scope = SCOPE_DASHBOARD_READ

    def get(self, request):
        company = request.auth.company
        if company is None:
            return api_error('Superuser tokens must specify a company.', code='NO_COMPANY', status=400)

        invoices_qs = Invoice.active_objects.filter(company=company)
        customers_qs = Customer.active_objects.filter(company=company)

        total_invoices = invoices_qs.count()
        total_customers = customers_qs.count()

        total_outstanding = (
            invoices_qs.aggregate(s=Sum('outstanding_balance'))['s'] or Decimal('0')
        )

        today = date.today()
        today_sales = (
            invoices_qs
            .filter(transaction_date=today, status='ISSUED')
            .aggregate(s=Sum('total'))['s'] or Decimal('0')
        )

        recent_invoices = (
            invoices_qs
            .select_related('customer')
            .prefetch_related('items__product', 'items__package')
            .order_by('-transaction_date', '-created_at')[:5]
        )

        dashboard_data = {
            'total_invoices': total_invoices,
            'total_customers': total_customers,
            'total_outstanding': total_outstanding,
            'today_sales': today_sales,
            'recent_invoices': recent_invoices,
        }

        serializer = DashboardSerializer(dashboard_data)
        return api_success(data=serializer.data)
