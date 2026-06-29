"""
Invoice views.

InvoiceListView    GET   /api/v1/invoices/
InvoiceDetailView  GET   /api/v1/invoices/<uuid:pk>/
InvoiceCreateView  POST  /api/v1/invoices/create/

All views use request.auth.company for tenant isolation.
Invoice creation is atomic and auto-generates invoice_number.
"""
import logging
from decimal import Decimal

from django.db import transaction
from django.db.models import Max
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView

from apps.api.authentication import APITokenAuthentication
from apps.api.pagination import paginate_queryset
from apps.api.permissions import HasAPIScope
from apps.api.response import api_error, api_list, api_success
from apps.api.scopes import SCOPE_INVOICES_READ, SCOPE_INVOICES_WRITE
from apps.api.serializers import InvoiceCreateSerializer, InvoiceSerializer
from apps.billing.models import Invoice, InvoiceItem
from apps.customers.models import Customer
from apps.products.models import Product

logger = logging.getLogger('audit')


class InvoiceListView(APIView):
    """
    GET /api/v1/invoices/

    Returns a paginated list of invoices for the token's company.
    Query params:
        ?status=ISSUED|DRAFT|CANCELLED
        ?customer=<uuid>
        ?from_date=YYYY-MM-DD
        ?to_date=YYYY-MM-DD
        ?page=<int>
        ?page_size=<int>  (max 100)
    """
    authentication_classes = [APITokenAuthentication]
    permission_classes = [HasAPIScope]
    required_scope = SCOPE_INVOICES_READ

    def get(self, request):
        company = request.auth.company
        if company is None:
            return api_error('Superuser tokens must specify a company.', code='NO_COMPANY', status=400)

        qs = (
            Invoice.active_objects
            .filter(company=company)
            .select_related('customer')
            .prefetch_related('items__product', 'items__package')
            .order_by('-transaction_date', '-created_at')
        )

        status_param = request.GET.get('status', '').strip().upper()
        if status_param:
            qs = qs.filter(status=status_param)

        customer_param = request.GET.get('customer', '').strip()
        if customer_param:
            qs = qs.filter(customer__id=customer_param)

        from_date = request.GET.get('from_date', '').strip()
        if from_date:
            qs = qs.filter(transaction_date__gte=from_date)

        to_date = request.GET.get('to_date', '').strip()
        if to_date:
            qs = qs.filter(transaction_date__lte=to_date)

        page_data, total, total_pages, page = paginate_queryset(qs, request)
        page_size = int(request.GET.get('page_size', 20))

        data = InvoiceSerializer(page_data, many=True).data
        return api_list(
            data=data,
            pagination={
                'total': total,
                'page': page,
                'page_size': min(page_size, 100),
                'total_pages': total_pages,
            },
        )


class InvoiceDetailView(APIView):
    """
    GET /api/v1/invoices/<uuid:pk>/

    Returns a single invoice with all items.
    Ownership is verified against the token's company.
    """
    authentication_classes = [APITokenAuthentication]
    permission_classes = [HasAPIScope]
    required_scope = SCOPE_INVOICES_READ

    def get(self, request, pk):
        company = request.auth.company
        if company is None:
            return api_error('Superuser tokens must specify a company.', code='NO_COMPANY', status=400)

        invoice = get_object_or_404(
            Invoice.active_objects.select_related('customer').prefetch_related(
                'items__product', 'items__package'
            ),
            pk=pk,
            company=company,
        )
        data = InvoiceSerializer(invoice).data
        return api_success(data=data)


class InvoiceCreateView(APIView):
    """
    POST /api/v1/invoices/create/

    Creates an Invoice + InvoiceItems atomically.
    - Status is set to ISSUED immediately (API invoices are always issued).
    - invoice_number is auto-generated as INV-{company_id_short}-{seq:05d}.
    - sequence_number is max(existing) + 1 per company, computed inside the transaction.
    """
    authentication_classes = [APITokenAuthentication]
    permission_classes = [HasAPIScope]
    required_scope = SCOPE_INVOICES_WRITE

    def post(self, request):
        company = request.auth.company
        if company is None:
            return api_error('Superuser tokens must specify a company.', code='NO_COMPANY', status=400)

        serializer = InvoiceCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return api_error(str(serializer.errors), code='VALIDATION_ERROR', status=400)

        data = serializer.validated_data

        # Resolve customer
        customer = None
        customer_id = data.get('customer_id')
        if customer_id:
            try:
                customer = Customer.active_objects.get(pk=customer_id, company=company)
            except Customer.DoesNotExist:
                return api_error('Customer not found.', code='CUSTOMER_NOT_FOUND', status=404)

        try:
            invoice = self._create_invoice(request, company, customer, data)
        except ValueError as exc:
            return api_error(str(exc), code='INVOICE_CREATE_ERROR', status=400)

        logger.info(
            'INVOICE_CREATED_API actor=%s invoice=%s company=%s',
            request.user.email, invoice.invoice_number, company.name,
        )

        result = InvoiceSerializer(
            Invoice.active_objects.prefetch_related('items__product', 'items__package')
            .select_related('customer')
            .get(pk=invoice.pk)
        ).data
        return api_success(data=result, message='Invoice created successfully.', status=201)

    @transaction.atomic
    def _create_invoice(self, request, company, customer, data):
        """Create invoice and items inside a single DB transaction."""
        # Auto-generate sequence number (per company, max + 1)
        max_seq = Invoice.objects.filter(company=company).aggregate(
            m=Max('sequence_number')
        )['m'] or 0
        sequence_number = max_seq + 1

        # Build invoice_number: INV-{first 8 chars of company id}-{seq:05d}
        company_id_short = str(company.id).replace('-', '')[:8].upper()
        invoice_number = f'INV-{company_id_short}-{sequence_number:05d}'

        tax_percent = Decimal(str(data.get('tax_percent', 0)))
        discount_percent = Decimal(str(data.get('discount_percent', 0)))

        invoice = Invoice.objects.create(
            company=company,
            customer=customer,
            invoice_number=invoice_number,
            sequence_number=sequence_number,
            transaction_date=data['transaction_date'],
            due_date=data.get('due_date'),
            tax_percent=tax_percent,
            discount_percent=discount_percent,
            status='ISSUED',
            total=Decimal('0.00'),
            created_by=request.user,
        )

        # Create items
        for item_data in data['items']:
            product_id = item_data.get('product_id')
            try:
                product = Product.active_objects.get(pk=product_id, company=company)
            except Product.DoesNotExist:
                raise ValueError(f'Product {product_id} not found.')

            quantity = int(item_data.get('quantity', 1))
            price = Decimal(str(item_data.get('price', product.price)))
            item_discount_percent = Decimal(str(item_data.get('discount_percent', 0)))

            InvoiceItem.objects.create(
                invoice=invoice,
                product=product,
                quantity=quantity,
                price=price,
                discount_percent=item_discount_percent,
            )

        # Reload to get recalculated totals (InvoiceItem.save() updates them)
        invoice.refresh_from_db()
        return invoice
