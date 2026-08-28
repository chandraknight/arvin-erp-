"""
Restaurant order services.
All business logic lives here — views stay thin.
"""
import logging
from decimal import Decimal
from django.utils import timezone
from django.db import transaction
from django.db.models import Max

import nepali_datetime

from apps.company.models import Company, FiscalYear
from apps.restaurant.models import (
    DiningOrder, DiningOrderItem, PrintJob, PrinterStation,
    RestaurantTable,
)

logger = logging.getLogger(__name__)
audit = logging.getLogger('audit')


def generate_order_number(company_id: str):
    """
    Format: {COMPANY_PREFIX}-ORD-{FISCAL_YEAR}-{NNNN}, e.g. DPS-ORD-2082/83-0001.
    Race-safe, fiscal-year-scoped — same pattern as generate_invoice_number.
    Returns (order_number, sequence, fiscal_year).
    """
    today_np = nepali_datetime.date.today()
    fiscal_year = None
    try:
        company = Company.active_objects.get(id=company_id)
        company_prefix = company.name[:3].upper().strip().ljust(3, 'X')
        fiscal_year = FiscalYear.active_objects.filter(is_active=True, company=company).first()
        fiscal_year_name = fiscal_year.name if fiscal_year else today_np.strftime("%y/%m/%d")
    except (Company.DoesNotExist, AttributeError):
        company_prefix = "ORD"
        fiscal_year_name = today_np.strftime("%y/%m/%d")

    prefix = f"{company_prefix}-ORD-{fiscal_year_name}-"

    fy_filter = {'fiscal_year': fiscal_year} if fiscal_year else {'fiscal_year__isnull': True}
    with transaction.atomic():
        last_seq = DiningOrder.objects.select_for_update().filter(
            company_id=company_id,
            **fy_filter,
        ).aggregate(max_seq=Max('sequence_number'))

        sequence = (last_seq['max_seq'] or 0) + 1

        order_number = f"{prefix}{sequence:04d}"
        while DiningOrder.objects.filter(
            company_id=company_id, fiscal_year=fiscal_year, sequence_number=sequence
        ).exists() or DiningOrder.objects.filter(order_number=order_number).exists():
            sequence += 1
            order_number = f"{prefix}{sequence:04d}"

    return order_number, sequence, fiscal_year


def open_order(request, table: RestaurantTable, covers: int = 1,
               waiter_name: str = '', customer=None, notes: str = '') -> DiningOrder:
    """
    Open a new dining order on a table.
    Marks the table as OCCUPIED.
    """
    order_number, seq, fy = generate_order_number(str(request.user_company.pk))
    with transaction.atomic():
        order = DiningOrder.objects.create(
            company=request.user_company,
            branch=getattr(request, 'user_branch', None),
            table=table,
            order_number=order_number,
            sequence_number=seq,
            fiscal_year=fy,
            covers=covers,
            waiter_name=waiter_name,
            customer=customer,
            notes=notes,
            created_by=request.user,
        )
        table.status = 'OCCUPIED'
        table.save(update_fields=['status'])

        audit.info(
            'DINING_ORDER_OPENED order=%s table=%s actor=%s company=%s',
            order.order_number, table.table_number,
            request.user.email, request.user_company,
        )
    return order


def add_item(order: DiningOrder, product, quantity: Decimal,
             item_type: str, unit_price: Decimal = None,
             discount_percent: Decimal = Decimal('0'),
             tax_percent: Decimal = Decimal('0'), notes: str = '',
             created_by=None) -> DiningOrderItem:
    item = DiningOrderItem.objects.create(
        order=order,
        product=product,
        item_type=item_type,
        quantity=quantity,
        unit_price=unit_price if unit_price is not None else product.price,
        discount_percent=discount_percent,
        tax_percent=tax_percent,
        notes=notes,
        created_by=created_by,
    )
    order.recalculate_totals()
    return item


def update_item_quantity(item: DiningOrderItem, new_quantity: Decimal, request) -> DiningOrderItem:
    """Change an order item's quantity in place and recalculate order totals."""
    if item.order.status in ('BILLED', 'PAID', 'CANCELLED'):
        raise ValueError("Cannot modify items on a closed order.")
    if new_quantity <= 0:
        raise ValueError("Quantity must be greater than zero.")

    item.quantity = new_quantity
    item.updated_by = request.user
    item.save(update_fields=['quantity', 'updated_by'])
    item.order.recalculate_totals()

    audit.info(
        'ITEM_QUANTITY_UPDATED order=%s item=%s quantity=%s actor=%s',
        item.order.order_number, item.product.name, new_quantity, request.user.email,
    )
    return item


def apply_order_discount(order: DiningOrder, discount_percent: Decimal, reason: str, request) -> DiningOrder:
    """
    Apply an order-level discount on top of item-level discounts.
    Requires a non-empty reason and an authorizing admin user.
    """
    if order.status in ('BILLED', 'PAID', 'CANCELLED'):
        raise ValueError("Cannot discount a closed order.")
    if not reason or not reason.strip():
        raise ValueError("A reason is required to apply an order discount.")
    if discount_percent < 0 or discount_percent > 100:
        raise ValueError("Discount percent must be between 0 and 100.")
    if not (request.user.is_superuser or getattr(request.user, 'is_company_admin', False)):
        raise ValueError("Only a company admin can authorize an order-level discount.")

    with transaction.atomic():
        order.discount_percent = discount_percent
        order.discount_reason = reason.strip()
        order.updated_by = request.user
        order.save(update_fields=['discount_percent', 'discount_reason', 'updated_by'])
        order.recalculate_totals()

        audit.info(
            'ORDER_DISCOUNT_APPLIED order=%s percent=%s reason=%s authorized_by=%s',
            order.order_number, discount_percent, reason.strip(), request.user.email,
        )
    return order


def _build_kot_payload(order: DiningOrder) -> dict:
    """Serialise unprinted food items for the KOT print job."""
    items = list(order.unprinted_food_items)
    return {
        'order_number': order.order_number,
        'table': order.table.label,
        'section': order.table.section.name if order.table.section else '',
        'covers': order.covers,
        'waiter': order.waiter_name or '',
        'printed_at': timezone.now().isoformat(),
        'items': [
            {
                'name': i.product.name,
                'qty': str(i.quantity),
                'notes': i.notes or '',
            }
            for i in items
        ],
    }


def _build_bot_payload(order: DiningOrder) -> dict:
    """Serialise unprinted beverage items for the BOT print job."""
    items = list(order.unprinted_beverage_items)
    return {
        'order_number': order.order_number,
        'table': order.table.label,
        'section': order.table.section.name if order.table.section else '',
        'covers': order.covers,
        'waiter': order.waiter_name or '',
        'printed_at': timezone.now().isoformat(),
        'items': [
            {
                'name': i.product.name,
                'qty': str(i.quantity),
                'notes': i.notes or '',
            }
            for i in items
        ],
    }


def _build_bill_payload(order: DiningOrder) -> dict:
    """Serialise the full order for the bill printer."""
    return {
        'order_number': order.order_number,
        'table': order.table.label,
        'covers': order.covers,
        'waiter': order.waiter_name or '',
        'printed_at': timezone.now().isoformat(),
        'items': [
            {
                'name': i.product.name,
                'qty': str(i.quantity),
                'unit_price': str(i.unit_price),
                'discount': str(i.discount_amount),
                'tax': str(i.tax_amount),
                'total': str(i.line_total),
            }
            for i in order.items.exclude(status='CANCELLED')
        ],
        'subtotal': str(order.subtotal),
        'discount': str(order.discount_amount),
        'tax': str(order.tax_amount),
        'total': str(order.total),
    }


def print_kot(order: DiningOrder, request) -> PrintJob | None:
    """
    Create a KOT PrintJob for all unprinted food items.
    Marks those items kot_printed=True and updates order status.
    Returns None if there are no unprinted food items.
    """
    items = list(order.unprinted_food_items)
    if not items:
        return None

    printer = PrinterStation.active_objects.filter(
        company=order.company, printer_type='KOT', is_active=True, is_default=True
    ).first() or PrinterStation.active_objects.filter(
        company=order.company, printer_type='KOT', is_active=True
    ).first()

    with transaction.atomic():
        job = PrintJob.objects.create(
            company=order.company,
            printer=printer,
            dining_order=order,
            job_type='KOT',
            status='QUEUED',
            payload=_build_kot_payload(order),
            created_by=request.user,
        )
        # Mark items as printed
        DiningOrderItem.objects.filter(
            pk__in=[i.pk for i in items]
        ).update(kot_printed=True, status='PREPARING')

        if order.status == 'OPEN':
            order.status = 'KOT_SENT'
            order.save(update_fields=['status'])

        audit.info(
            'KOT_PRINTED order=%s items=%d actor=%s',
            order.order_number, len(items), request.user.email,
        )
    return job


def print_bot(order: DiningOrder, request) -> PrintJob | None:
    """
    Create a BOT PrintJob for all unprinted beverage items.
    Marks those items bot_printed=True and updates order status.
    Returns None if there are no unprinted beverage items.
    """
    items = list(order.unprinted_beverage_items)
    if not items:
        return None

    printer = PrinterStation.active_objects.filter(
        company=order.company, printer_type='BOT', is_active=True, is_default=True
    ).first() or PrinterStation.active_objects.filter(
        company=order.company, printer_type='BOT', is_active=True
    ).first()

    with transaction.atomic():
        job = PrintJob.objects.create(
            company=order.company,
            printer=printer,
            dining_order=order,
            job_type='BOT',
            status='QUEUED',
            payload=_build_bot_payload(order),
            created_by=request.user,
        )
        DiningOrderItem.objects.filter(
            pk__in=[i.pk for i in items]
        ).update(bot_printed=True, status='PREPARING')

        if order.status == 'OPEN':
            order.status = 'BOT_SENT'
            order.save(update_fields=['status'])

        audit.info(
            'BOT_PRINTED order=%s items=%d actor=%s',
            order.order_number, len(items), request.user.email,
        )
    return job


def _create_invoice_for_items(order: DiningOrder, items, discount_percent: Decimal, request):
    """
    Create one Invoice covering the given (non-cancelled) DiningOrderItems.
    discount_percent is the order-level discount to apply proportionally to this portion.
    Marks each item.invoice. Does not touch order/table status — caller's job.
    """
    from apps.billing.models import Invoice, InvoiceItem
    from apps.billing.services.invoice_service import generate_invoice_number, vat_invoice_fields
    from django.utils import timezone as tz

    items = list(items)
    item_subtotal = sum(i.line_subtotal for i in items)
    item_discount = sum(i.discount_amount for i in items)
    tax = sum(i.tax_amount for i in items)
    order_discount = ((item_subtotal - item_discount) * discount_percent / 100).quantize(Decimal('0.01'))
    total_discount = item_discount + order_discount
    total = item_subtotal - total_discount + tax

    vat_fields = vat_invoice_fields(order.company)
    invoice_number, seq, fy = generate_invoice_number(order.company.id, doc_type=vat_fields['doc_type'])
    invoice = Invoice.objects.create(
        company=order.company,
        branch=order.branch,
        customer=order.customer,
        invoice_number=invoice_number,
        fiscal_year=fy,
        transaction_date=tz.now().date(),
        subtotal=item_subtotal,
        discount_amount=total_discount,
        tax_amount=tax,
        total=total,
        outstanding_balance=total,
        tax_percent=vat_fields['tax_percent'],
        status=vat_fields['status'],
        sequence_number=seq,
        created_by=request.user,
    )

    for item in items:
        InvoiceItem.objects.create(
            invoice=invoice,
            product=item.product,
            description=item.product.name,
            quantity=int(item.quantity),
            price=item.unit_price,
            discount_percent=item.discount_percent,
        )

    DiningOrderItem.objects.filter(pk__in=[i.pk for i in items]).update(invoice=invoice)

    printer = PrinterStation.active_objects.filter(
        company=order.company, printer_type='BILL', is_active=True, is_default=True
    ).first() or PrinterStation.active_objects.filter(
        company=order.company, printer_type='BILL', is_active=True
    ).first()

    PrintJob.objects.create(
        company=order.company,
        printer=printer,
        dining_order=order,
        job_type='BILL',
        status='QUEUED',
        payload=_build_bill_payload(order),
        created_by=request.user,
    )
    return invoice


def issue_bill(order: DiningOrder, request):
    """
    Convert a DiningOrder to an Invoice.
    Sets order status to BILLED and table status to CLEANING.
    Returns the created Invoice.
    """
    from apps.company.services.company_services import setup_default_ledger_accounts
    from django.utils import timezone as tz

    if order.status in ('BILLED', 'PAID', 'CANCELLED'):
        raise ValueError(f"Order {order.order_number} is already {order.status}.")
    if order.total <= 0:
        raise ValueError("Cannot bill an order with no items or zero total.")

    setup_default_ledger_accounts(order.company)

    with transaction.atomic():
        items = order.items.exclude(status='CANCELLED')
        invoice = _create_invoice_for_items(order, items, order.discount_percent, request)

        order.invoice = invoice
        order.status = 'BILLED'
        order.closed_at = tz.now()
        order.save(update_fields=['invoice', 'status', 'closed_at'])

        order.table.status = 'CLEANING'
        order.table.save(update_fields=['status'])

        audit.info(
            'BILL_ISSUED order=%s invoice=%s actor=%s company=%s',
            order.order_number, invoice.invoice_number,
            request.user.email, order.company,
        )

    return invoice


def split_bill(order: DiningOrder, splits: list, request) -> list:
    """
    Split a DiningOrder's bill into multiple invoices.
    Each split dict is either:
      {'mode': 'even', 'item_ids': [...]}   -- caller pre-partitions items evenly
      {'mode': 'items', 'item_ids': [...]}  -- staff-selected items per split
    Every non-cancelled item must be covered by exactly one split.
    Sets order to BILLED and table to CLEANING once all items are covered.
    Returns the list of created Invoices.
    """
    from apps.company.services.company_services import setup_default_ledger_accounts
    from django.utils import timezone as tz

    if order.status in ('BILLED', 'PAID', 'CANCELLED'):
        raise ValueError(f"Order {order.order_number} is already {order.status}.")
    if not splits:
        raise ValueError("At least one split is required.")

    active_items = list(order.items.exclude(status='CANCELLED'))
    active_ids = {i.pk for i in active_items}
    covered_ids = set()
    for split in splits:
        item_ids = {item_id for item_id in split.get('item_ids', [])}
        if not item_ids:
            raise ValueError("Each split must include at least one item.")
        if not item_ids.issubset(active_ids):
            raise ValueError("A split references an item not on this order.")
        if item_ids & covered_ids:
            raise ValueError("An item was assigned to more than one split.")
        covered_ids |= item_ids

    if covered_ids != active_ids:
        raise ValueError("All order items must be covered by some split.")

    setup_default_ledger_accounts(order.company)

    with transaction.atomic():
        invoices = []
        items_by_id = {i.pk: i for i in active_items}
        for split in splits:
            split_items = [items_by_id[item_id] for item_id in split['item_ids']]
            invoice = _create_invoice_for_items(order, split_items, order.discount_percent, request)
            invoices.append(invoice)

        order.invoice = invoices[0]
        order.status = 'BILLED'
        order.closed_at = tz.now()
        order.save(update_fields=['invoice', 'status', 'closed_at'])

        order.table.status = 'CLEANING'
        order.table.save(update_fields=['status'])

        audit.info(
            'BILL_SPLIT order=%s invoices=%s actor=%s company=%s',
            order.order_number, ','.join(i.invoice_number for i in invoices),
            request.user.email, order.company,
        )

    return invoices


def merge_orders(source_order: DiningOrder, target_order: DiningOrder, request) -> DiningOrder:
    """
    Merge source_order's items into target_order. Cancels source_order and
    frees its table. target_order's table stays OCCUPIED.
    """
    OPEN_STATUSES = ('OPEN', 'KOT_SENT', 'BOT_SENT')

    if source_order.pk == target_order.pk:
        raise ValueError("Cannot merge an order into itself.")
    if source_order.company_id != target_order.company_id:
        raise ValueError("Orders belong to different companies.")
    if source_order.status not in OPEN_STATUSES:
        raise ValueError(f"Source order is {source_order.status} — only open orders can be merged.")
    if target_order.status not in OPEN_STATUSES:
        raise ValueError(f"Target order is {target_order.status} — only open orders can be merged.")

    with transaction.atomic():
        source_order.items.exclude(status='CANCELLED').update(order=target_order)
        target_order.recalculate_totals()

        source_table = source_order.table
        source_order.status = 'CANCELLED'
        source_order.notes = (source_order.notes or '') + f'\nMerged into {target_order.order_number}'
        source_order.closed_at = timezone.now()
        source_order.save(update_fields=['status', 'notes', 'closed_at'])

        source_table.status = 'AVAILABLE'
        source_table.save(update_fields=['status'])

        audit.info(
            'ORDERS_MERGED source=%s target=%s actor=%s',
            source_order.order_number, target_order.order_number, request.user.email,
        )
    return target_order


def transfer_table(order: DiningOrder, target_table: RestaurantTable, request) -> DiningOrder:
    """
    Move an open order from its current table to target_table.
    Old table → AVAILABLE, new table → OCCUPIED.
    """
    if target_table.status != 'AVAILABLE':
        raise ValueError(f"Table {target_table.label} is not available.")

    with transaction.atomic():
        old_table = order.table

        order.table = target_table
        order.updated_by = request.user
        order.save(update_fields=['table', 'updated_by'])

        old_table.status = 'AVAILABLE'
        old_table.save(update_fields=['status'])

        target_table.status = 'OCCUPIED'
        target_table.save(update_fields=['status'])

        audit.info(
            'TABLE_TRANSFER order=%s from=%s to=%s actor=%s',
            order.order_number, old_table.table_number,
            target_table.table_number, request.user.email,
        )
    return order


def close_order_paid(order: DiningOrder, request):
    """Mark a BILLED order as PAID and free the table."""
    from apps.billing.models import Invoice
    with transaction.atomic():
        order.status = 'PAID'
        order.save(update_fields=['status'])
        order.table.status = 'AVAILABLE'
        order.table.save(update_fields=['status'])
        # Zero the linked invoice's outstanding balance so AR aging is correct
        if order.invoice_id:
            Invoice.objects.filter(pk=order.invoice_id).update(outstanding_balance=0)
        audit.info(
            'ORDER_PAID order=%s actor=%s', order.order_number, request.user.email
        )


def reprint_kot(order: DiningOrder, request) -> PrintJob | None:
    """
    Force-reprint the KOT for ALL food items (already printed or not).
    Does NOT change item status — use when kitchen needs a duplicate.
    """
    items = list(order.items.filter(item_type='FOOD').exclude(status='CANCELLED'))
    if not items:
        return None

    printer = (
        PrinterStation.active_objects.filter(
            company=order.company, printer_type='KOT', is_active=True, is_default=True
        ).first()
        or PrinterStation.active_objects.filter(
            company=order.company, printer_type='KOT', is_active=True
        ).first()
    )

    payload = {
        'order_number': order.order_number,
        'table': order.table.label,
        'section': order.table.section.name if order.table.section else '',
        'covers': order.covers,
        'waiter': order.waiter_name or '',
        'printed_at': timezone.now().isoformat(),
        'reprint': True,
        'items': [{'name': i.product.name, 'qty': str(i.quantity), 'notes': i.notes or ''} for i in items],
    }
    job = PrintJob.objects.create(
        company=order.company, printer=printer, dining_order=order,
        job_type='KOT', status='QUEUED', payload=payload, created_by=request.user,
    )
    audit.info('KOT_REPRINTED order=%s items=%d actor=%s', order.order_number, len(items), request.user.email)
    return job


def reprint_bot(order: DiningOrder, request) -> PrintJob | None:
    """Force-reprint the BOT for ALL beverage items."""
    items = list(order.items.filter(item_type='BEVERAGE').exclude(status='CANCELLED'))
    if not items:
        return None

    printer = (
        PrinterStation.active_objects.filter(
            company=order.company, printer_type='BOT', is_active=True, is_default=True
        ).first()
        or PrinterStation.active_objects.filter(
            company=order.company, printer_type='BOT', is_active=True
        ).first()
    )

    payload = {
        'order_number': order.order_number,
        'table': order.table.label,
        'section': order.table.section.name if order.table.section else '',
        'covers': order.covers,
        'waiter': order.waiter_name or '',
        'printed_at': timezone.now().isoformat(),
        'reprint': True,
        'items': [{'name': i.product.name, 'qty': str(i.quantity), 'notes': i.notes or ''} for i in items],
    }
    job = PrintJob.objects.create(
        company=order.company, printer=printer, dining_order=order,
        job_type='BOT', status='QUEUED', payload=payload, created_by=request.user,
    )
    audit.info('BOT_REPRINTED order=%s items=%d actor=%s', order.order_number, len(items), request.user.email)
    return job


def send_kot_and_bot(order: DiningOrder, request) -> tuple:
    """Send KOT and BOT together in one action. Returns (kot_job, bot_job)."""
    kot_job = print_kot(order, request)
    bot_job = print_bot(order, request)
    return kot_job, bot_job


def void_order(order: DiningOrder, reason: str, request) -> DiningOrder:
    """
    Cancel an entire open/in-progress order.
    - Marks all non-cancelled items CANCELLED
    - Frees the table
    - Status → CANCELLED
    Cannot void a BILLED or PAID order (use a credit note instead).
    """
    if order.status in ('BILLED', 'PAID'):
        raise ValueError(f"Order {order.order_number} is {order.status} — issue a credit note to reverse it.")
    if order.status == 'CANCELLED':
        raise ValueError(f"Order {order.order_number} is already cancelled.")

    with transaction.atomic():
        order.items.exclude(status='CANCELLED').update(status='CANCELLED')
        order.status = 'CANCELLED'
        order.notes = (order.notes or '') + f'\nVOIDED: {reason}'
        order.closed_at = timezone.now()
        order.save(update_fields=['status', 'notes', 'closed_at'])

        order.table.status = 'AVAILABLE'
        order.table.save(update_fields=['status'])

        audit.info(
            'ORDER_VOIDED order=%s reason=%s actor=%s',
            order.order_number, reason, request.user.email,
        )
    return order


def update_item_status(item: DiningOrderItem, new_status: str, request) -> DiningOrderItem:
    """
    Update a single item's status: PREPARING → READY → SERVED.
    Allowed transitions only — no backwards moves.
    """
    ALLOWED = {
        'PREPARING': 'READY',
        'READY': 'SERVED',
    }
    if item.status not in ALLOWED:
        raise ValueError(f"Cannot advance item from '{item.status}'.")
    if new_status != ALLOWED[item.status]:
        raise ValueError(f"Invalid transition: {item.status} → {new_status}.")

    item.status = new_status
    item.updated_by = request.user
    item.save(update_fields=['status', 'updated_by'])
    audit.info(
        'ITEM_STATUS order=%s item=%s status=%s actor=%s',
        item.order.order_number, item.product.name, new_status, request.user.email,
    )
    return item
