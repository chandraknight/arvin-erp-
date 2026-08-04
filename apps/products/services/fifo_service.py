"""NFRS 2 (IAS 2) FIFO inventory costing — for products with cost_method == 'FIFO'."""
import logging
from decimal import Decimal

from django.db import transaction

logger = logging.getLogger(__name__)


def create_lot(product, qty, unit_cost, source_reference=''):
    """Record a new receipt lot and sync product.cost_price to the new lot's cost."""
    from ..models import StockLot

    lot = StockLot.objects.create(
        product=product,
        qty_received=qty,
        qty_remaining=qty,
        unit_cost=unit_cost,
        source_reference=source_reference,
    )
    product.cost_price = unit_cost
    product.save(update_fields=['cost_price'])
    return lot


@transaction.atomic
def consume_fifo_lots(product, qty) -> Decimal:
    """
    Deduct `qty` from the oldest remaining lots first.

    Returns the total cost of the quantity consumed. Any quantity not
    covered by existing lots (e.g. stock predating this feature) is priced
    at the product's current cost_price.
    """
    from ..models import StockLot

    remaining = int(qty)
    total_cost = Decimal('0')

    lots = StockLot.objects.select_for_update().filter(
        product=product, qty_remaining__gt=0
    ).order_by('received_at')

    for lot in lots:
        if remaining <= 0:
            break
        take = min(remaining, lot.qty_remaining)
        total_cost += Decimal(take) * lot.unit_cost
        lot.qty_remaining -= take
        lot.save(update_fields=['qty_remaining'])
        remaining -= take

    if remaining > 0:
        # Lots don't cover the full quantity — likely stock recorded before this
        # product had FIFO lots, or a manual adjustment that bypassed lot creation.
        logger.warning(
            'fifo_lot_shortfall product=%s requested=%s covered_by_lots=%s falling_back_to_cost_price=%s',
            product.id, qty, int(qty) - remaining, product.cost_price,
        )
        total_cost += Decimal(remaining) * (product.cost_price or Decimal('0'))

    oldest_remaining = StockLot.objects.filter(
        product=product, qty_remaining__gt=0
    ).order_by('received_at').first()
    if oldest_remaining and oldest_remaining.unit_cost != product.cost_price:
        product.cost_price = oldest_remaining.unit_cost
        product.save(update_fields=['cost_price'])

    return total_cost


def fifo_stock_value(product) -> Decimal:
    """Sum of qty_remaining * unit_cost across all lots — current FIFO carrying cost."""
    from ..models import StockLot

    total = Decimal('0')
    for lot in StockLot.objects.filter(product=product, qty_remaining__gt=0):
        total += Decimal(lot.qty_remaining) * lot.unit_cost
    return total
