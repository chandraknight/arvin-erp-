from django.db import transaction
from django.db.models import F, Max
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


def record_delivery_payment(delivery, amount, method, user, bank_account=None):
    """
    Create a Payment for cash/bank/online collected at the door and reduce
    the linked Invoice's outstanding_balance. Supports partial payment —
    amount may be less than outstanding_balance. Mirrors
    apps.ecom.services.record_ecom_payment. Returns None if there's no
    invoice or nothing left to collect.
    """
    from decimal import Decimal

    from apps.payments.models import Payment
    from apps.payments.services.payment_number_service import generate_payment_number

    order = delivery.sales_order
    invoice = order.invoice if order else None
    if not invoice or invoice.outstanding_balance <= Decimal('0.00'):
        return None

    amount = min(Decimal(amount), invoice.outstanding_balance)
    if amount <= Decimal('0.00'):
        return None

    try:
        reference_number, _, pay_fy = generate_payment_number(delivery.company.id, 'CUSTOMER')
    except Exception:
        reference_number, pay_fy = None, None

    with transaction.atomic():
        payment = Payment.objects.create(
            company=delivery.company,
            branch=order.branch,
            invoice=invoice,
            date=timezone.now().date(),
            amount=amount,
            amount_applied=amount,
            method=method,
            payment_type='CUSTOMER',
            bank_account=bank_account,
            reference_number=reference_number,
            fiscal_year=pay_fy,
            description=f'Collected at delivery {delivery.delivery_number}',
            created_by=user,
        )

        invoice.outstanding_balance -= amount
        invoice.save(update_fields=['outstanding_balance'])

    return payment


def dispatch_stock_and_cogs(delivery_note, user):
    """
    Decrement inventory and post the COGS/Inventory journal entry for the
    goods leaving the warehouse on this delivery note. Called at dispatch
    (DeliveryNote creation) — the moment stock actually leaves, not at
    later delivery confirmation. Mirrors apps.pos.services.checkout_services
    .checkout()'s stock-decrement + FIFO cost + post_cogs_journal pattern.

    Skips service items and companies with inventory tracking disabled.
    Does not validate stock availability — a sales order can be dispatched
    against negative stock the same way POS does not block a sale when no
    ProductStock record exists (treated as unlimited).
    """
    from decimal import Decimal

    from apps.products.models import Product, ProductStock, StockTransaction

    company = delivery_note.company
    if not getattr(company, 'enable_inventory', False):
        return

    total_cogs = Decimal('0.00')
    for item in delivery_note.items.filter(is_deleted=False).select_related('order_item__product'):
        product = item.order_item.product
        qty = int(item.quantity_delivered)
        if not product or product.is_service or qty <= 0:
            continue

        if product.cost_method == 'FIFO':
            from apps.products.services.fifo_service import consume_fifo_lots
            total_cogs += consume_fifo_lots(product, qty)
        else:
            total_cogs += Decimal(qty) * (product.cost_price or Decimal('0.00'))

        ProductStock.objects.filter(product=product).update(stock=F('stock') - qty)
        StockTransaction.objects.create(
            product=product,
            user=user,
            transaction_type='REMOVE',
            quantity=qty,
            reason=f'Delivery {delivery_note.delivery_number}',
        )

    if total_cogs > Decimal('0.00'):
        from apps.products.services.cogs_service import post_cogs_journal
        post_cogs_journal(
            company=company,
            description=f'COGS — Delivery {delivery_note.delivery_number}',
            total_cost=total_cogs,
            posted_by=user,
        )
