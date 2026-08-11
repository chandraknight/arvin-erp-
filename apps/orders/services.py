from django.db import transaction
from django.db.models import Max
from django.utils import timezone

import nepali_datetime

from apps.billing.models import Invoice, InvoiceItem
from apps.billing.services.invoice_service import generate_invoice_number, vat_invoice_fields
from apps.company.models import Company, FiscalYear
from apps.company.services.company_services import setup_default_ledger_accounts


def generate_sales_order_number(company_id):
    """
    Format: {COMPANY_PREFIX}-SO-{FISCAL_YEAR}-{NNNN}, e.g. DPS-SO-2082/83-0001.
    Same fiscal-year-scoped, race-safe pattern as generate_invoice_number —
    sequence resets to 0001 for each new fiscal year.
    Returns (order_number, sequence, fiscal_year).
    """
    from apps.orders.models import SalesOrder

    today_np = nepali_datetime.date.today()
    fiscal_year = None
    try:
        company = Company.active_objects.get(id=company_id)
        company_prefix = company.name[:3].upper().strip().ljust(3, 'X')
        fiscal_year = FiscalYear.active_objects.filter(is_active=True, company=company).first()
        fiscal_year_name = fiscal_year.name if fiscal_year else today_np.strftime("%y/%m/%d")
    except (Company.DoesNotExist, AttributeError):
        company_prefix = "SO"
        fiscal_year_name = today_np.strftime("%y/%m/%d")

    prefix = f"{company_prefix}-SO-{fiscal_year_name}-"

    fy_filter = {'fiscal_year': fiscal_year} if fiscal_year else {'fiscal_year__isnull': True}
    with transaction.atomic():
        last_seq = SalesOrder.objects.select_for_update().filter(
            company_id=company_id,
            **fy_filter,
        ).aggregate(max_seq=Max('sequence_number'))

        sequence = (last_seq['max_seq'] or 0) + 1

        order_number = f"{prefix}{sequence:04d}"
        while SalesOrder.objects.filter(
            company_id=company_id, fiscal_year=fiscal_year, sequence_number=sequence
        ).exists() or SalesOrder.objects.filter(order_number=order_number).exists():
            sequence += 1
            order_number = f"{prefix}{sequence:04d}"

    return order_number, sequence, fiscal_year


def generate_delivery_note_number(company_id):
    """
    Format: {COMPANY_PREFIX}-DN-{FISCAL_YEAR}-{NNNN}, e.g. DPS-DN-2082/83-0001.
    Same fiscal-year-scoped, race-safe pattern as generate_sales_order_number.
    Returns (delivery_number, sequence, fiscal_year).
    """
    from apps.orders.models import DeliveryNote

    today_np = nepali_datetime.date.today()
    fiscal_year = None
    try:
        company = Company.active_objects.get(id=company_id)
        company_prefix = company.name[:3].upper().strip().ljust(3, 'X')
        fiscal_year = FiscalYear.active_objects.filter(is_active=True, company=company).first()
        fiscal_year_name = fiscal_year.name if fiscal_year else today_np.strftime("%y/%m/%d")
    except (Company.DoesNotExist, AttributeError):
        company_prefix = "DN"
        fiscal_year_name = today_np.strftime("%y/%m/%d")

    prefix = f"{company_prefix}-DN-{fiscal_year_name}-"

    fy_filter = {'fiscal_year': fiscal_year} if fiscal_year else {'fiscal_year__isnull': True}
    with transaction.atomic():
        last_seq = DeliveryNote.objects.select_for_update().filter(
            company_id=company_id,
            **fy_filter,
        ).aggregate(max_seq=Max('sequence_number'))

        sequence = (last_seq['max_seq'] or 0) + 1

        delivery_number = f"{prefix}{sequence:04d}"
        while DeliveryNote.objects.filter(
            company_id=company_id, fiscal_year=fiscal_year, sequence_number=sequence
        ).exists() or DeliveryNote.objects.filter(delivery_number=delivery_number).exists():
            sequence += 1
            delivery_number = f"{prefix}{sequence:04d}"

    return delivery_number, sequence, fiscal_year


def create_invoice_from_sales_order(order, user):
    """Create an Invoice + InvoiceItems from a SalesOrder. Idempotent — returns
    the existing invoice if one is already linked. Does not touch order.status;
    callers decide what a newly-invoiced order's status should be."""
    if order.invoice_id:
        return order.invoice

    company = order.company
    setup_default_ledger_accounts(company)

    vat_fields = vat_invoice_fields(company)
    invoice_number, seq, fy = generate_invoice_number(company.id, doc_type=vat_fields['doc_type'])

    invoice = Invoice.objects.create(
        company=company,
        customer=order.customer,
        branch=order.branch,
        transaction_date=timezone.now().date(),
        subtotal=order.subtotal,
        discount_amount=order.discount_amount,
        tax_amount=order.tax_amount,
        total=order.total,
        outstanding_balance=order.total,
        tax_percent=vat_fields['tax_percent'],
        invoice_number=invoice_number,
        fiscal_year=fy,
        sequence_number=seq,
        status=vat_fields['status'],
        created_by=user,
    )

    for item in order.items.filter(is_deleted=False):
        InvoiceItem.objects.create(
            invoice=invoice,
            product=item.product,
            description=item.description or (item.product.name if item.product else ''),
            quantity=int(item.quantity),
            price=item.unit_price,
            discount_percent=item.discount_percent,
        )

    order.invoice = invoice
    order.save(update_fields=['invoice'])

    return invoice
