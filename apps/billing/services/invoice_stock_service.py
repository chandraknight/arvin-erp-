"""
Issue stock and recognise COGS for invoices raised outside POS / sales-order delivery
(manual billing screen, restaurant bills). POS and delivery notes do this themselves.

NFRS 2: when goods are sold, their cost leaves Inventory:
  DR Cost of Goods Sold / CR Inventory   (FIFO lot cost, or cost_price otherwise)

Idempotent via Invoice.stock_issued_at, so a re-save or retry never issues twice.
Service items, items without a product or stock record, and companies with inventory disabled are skipped.
"""
import logging
from decimal import Decimal

from django.db import transaction
from django.db.models import F
from django.utils import timezone

logger = logging.getLogger(__name__)


@transaction.atomic
def issue_invoice_stock(invoice, user=None):
    from apps.billing.models import Invoice
    from apps.products.models import ProductStock
    from apps.products.services.cogs_service import post_cogs_journal
    from apps.products.services.stock_ledger_service import log_movement

    # Lock the row so two concurrent saves can't both pass the idempotency check.
    invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
    company = invoice.company
    if invoice.stock_issued_at or not company or not company.enable_inventory:
        return None

    total_cogs = Decimal('0.00')
    for item in invoice.items.select_related('product').filter(product__isnull=False):
        product, qty = item.product, int(item.quantity)
        # No ProductStock row = product isn't stock-tracked (POS treats it as unlimited too).
        if product.is_service or qty <= 0 or not ProductStock.objects.filter(product=product).exists():
            continue

        if product.cost_method == 'FIFO':
            from apps.products.services.fifo_service import consume_fifo_lots
            line_cogs = consume_fifo_lots(product, qty)
        else:
            line_cogs = Decimal(qty) * (product.cost_price or Decimal('0.00'))
        total_cogs += line_cogs

        item.unit_cost = (line_cogs / Decimal(qty)).quantize(Decimal('0.0001'))
        item.save(update_fields=['unit_cost'])

        ProductStock.objects.filter(product=product).update(stock=F('stock') - qty)
        log_movement(
            product, transaction_type='REMOVE', quantity=qty, qty_change=-qty, user=user,
            reason=f'Invoice {invoice.invoice_number}', reference=invoice.invoice_number or '',
            unit_cost=item.unit_cost,
        )

    entry = post_cogs_journal(
        company=company, description=f'COGS — Invoice {invoice.invoice_number}',
        total_cost=total_cogs, posted_by=user, date=invoice.transaction_date,
    )
    Invoice.objects.filter(pk=invoice.pk).update(stock_issued_at=timezone.now())
    logger.info('invoice_stock_issued invoice=%s cogs=%s', invoice.invoice_number, total_cogs)
    return entry
