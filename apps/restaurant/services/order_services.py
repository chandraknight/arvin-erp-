"""
Restaurant order services.
All business logic lives here — views stay thin.
"""
import logging
from decimal import Decimal
from django.utils import timezone
from django.db import transaction

from apps.restaurant.models import (
    DiningOrder, DiningOrderItem, PrintJob, PrinterStation,
    RestaurantTable,
)

logger = logging.getLogger(__name__)
audit = logging.getLogger('audit')


def generate_order_number(company_id: str) -> str:
    """Generate a sequential order number like ORD-0001."""
    with transaction.atomic():
        # Order by created_at (not order_number string) to avoid lexicographic ordering bug
        # where 'ORD-0009' sorts after 'ORD-0010'.
        last = DiningOrder.objects.select_for_update().filter(
            company_id=company_id, order_number__startswith='ORD-'
        ).order_by('-created_at').first()
        if last and last.order_number:
            try:
                seq = int(last.order_number[4:]) + 1
            except ValueError:
                seq = DiningOrder.objects.filter(company_id=company_id).count() + 1
        else:
            seq = DiningOrder.objects.filter(company_id=company_id).count() + 1
    return f"ORD-{seq:04d}"


def open_order(request, table: RestaurantTable, covers: int = 1,
               waiter_name: str = '', customer=None, notes: str = '') -> DiningOrder:
    """
    Open a new dining order on a table.
    Marks the table as OCCUPIED.
    """
    with transaction.atomic():
        order = DiningOrder.objects.create(
            company=request.user_company,
            branch=getattr(request, 'user_branch', None),
            table=table,
            order_number=generate_order_number(str(request.user_company.pk)),
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


def issue_bill(order: DiningOrder, request):
    """
    Convert a DiningOrder to an Invoice.
    Sets order status to BILLED and table status to CLEANING.
    Returns the created Invoice.
    """
    from apps.billing.models import Invoice, InvoiceItem
    from apps.company.services.company_services import setup_default_ledger_accounts
    from django.utils import timezone as tz

    if order.status in ('BILLED', 'PAID', 'CANCELLED'):
        raise ValueError(f"Order {order.order_number} is already {order.status}.")
    if order.total <= 0:
        raise ValueError("Cannot bill an order with no items or zero total.")

    setup_default_ledger_accounts(order.company)

    from apps.billing.services.invoice_service import generate_invoice_number

    with transaction.atomic():
        invoice_number, seq = generate_invoice_number(order.company.id)
        invoice = Invoice.objects.create(
            company=order.company,
            branch=order.branch,
            customer=order.customer,
            invoice_number=invoice_number,
            transaction_date=tz.now().date(),
            subtotal=order.subtotal,
            discount_amount=order.discount_amount,
            tax_amount=order.tax_amount,
            total=order.total,
            outstanding_balance=order.total,
            tax_percent=order.company.tax_rate,
            sequence_number=seq,
            created_by=request.user,
        )

        for item in order.items.exclude(status='CANCELLED'):
            InvoiceItem.objects.create(
                invoice=invoice,
                product=item.product,
                description=item.product.name,
                quantity=int(item.quantity),
                price=item.unit_price,
                discount_percent=item.discount_percent,
            )

        # Create bill print job
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
