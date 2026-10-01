"""
Single entry point for writing the stock ledger (StockTransaction rows).

Every flow that moves inventory (purchase receipt, sale, delivery, production,
manual adjustment, write-off) logs through log_movement() so the Stock Register
can rely on `qty_change` (signed net change in total on-hand) and `unit_cost`.
"""
from decimal import Decimal


def log_movement(product, *, transaction_type, quantity, qty_change, stock_type='POS',
                 user=None, reason='', reference='', unit_cost=None, **extra):
    from ..models import StockTransaction

    if unit_cost is not None:
        unit_cost = Decimal(unit_cost).quantize(Decimal('0.0001'))
    return StockTransaction.objects.create(
        product=product,
        user=user,
        transaction_type=transaction_type,
        stock_type=stock_type,
        quantity=quantity,
        qty_change=qty_change,
        unit_cost=unit_cost,
        reason=reason,
        reference=reference,
        **extra,
    )


def apply_fifo_delta(product, delta):
    """
    Keep FIFO lots in step with a manual stock change (opening stock, manual
    add/remove/adjust) so stock_valuation matches on-hand quantity.

    Returns the unit cost of the movement (cost_price for adds; actual lot
    cost consumed for removals). No-op for non-FIFO products.
    """
    unit_cost = product.cost_price or Decimal('0')
    if product.cost_method != 'FIFO' or not delta:
        return unit_cost
    from .fifo_service import create_lot, consume_fifo_lots
    if delta > 0:
        create_lot(product, delta, unit_cost, source_reference='Manual stock add')
        return unit_cost
    return consume_fifo_lots(product, -delta) / Decimal(-delta)
