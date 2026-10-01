"""
NFRS 2 (IAS 2) — Inventory disposal / write-off service.

post_stock_disposal(product, quantity, disposal_reason, ..., posted_by)
  → reduces stock, posts a write-off journal (DR Inventory Write-off Expense,
    CR Inventory), and records the StockTransaction audit row.

Journal entry:
  DR  Inventory Write-off Expense     qty * cost_price
  CR  Inventory                       qty * cost_price

No ledger 'Inventory' account is otherwise posted on purchase/sale (see
apps/reports/views.py get_closing_stock_valuation docstring) — this credit
is a below-the-line correction against the computed closing-stock overlay,
mirroring how the write-off actually reduces qty-on-hand x cost_price.
"""
from __future__ import annotations

import logging
from decimal import Decimal

from django.db import transaction

logger = logging.getLogger(__name__)

_INVENTORY_WRITE_OFF_EXPENSE = 'Inventory Write-off Expense'
_INVENTORY_ACCOUNT = 'Inventory'


def _get_or_create_account(company, name, account_type, code=None):
    from apps.bookkeeping.models import LedgerAccount
    # LedgerAccount enforces uniqueness on (company, code), not (company, name) —
    # look up by code first so an existing account under a different name is
    # reused instead of get_or_create() raising IntegrityError on a duplicate code.
    if code:
        acc = LedgerAccount.objects.filter(company=company, code=code).first()
        if acc:
            return acc
    acc, _ = LedgerAccount.objects.get_or_create(
        company=company,
        name=name,
        defaults={
            'account_type': account_type,
            'code': code,
            'system_created': True,
        },
    )
    return acc


@transaction.atomic
def post_stock_disposal(
    product,
    quantity: int,
    disposal_reason: str,
    stock_type: str = 'POS',
    reason: str = '',
    posted_by=None,
):
    """
    Write off *quantity* units of *product* (NFRS 2).

    Raises ValueError if quantity <= 0 or insufficient stock on hand.
    Returns the created StockTransaction (with .journal_entry set).
    """
    from apps.products.models import ProductStock, StockTransaction
    from apps.bookkeeping.models import post_journal_entry

    if quantity <= 0:
        raise ValueError("Disposal quantity must be greater than zero.")

    company = product.company
    stock, _ = ProductStock.objects.select_for_update().get_or_create(product=product)

    if stock_type == 'ECOM':
        if stock.ecom_stock < quantity:
            raise ValueError(f"Insufficient e-commerce stock ({stock.ecom_stock}) to dispose {quantity}.")
        stock.ecom_stock -= quantity
        stock.save(update_fields=['ecom_stock', 'updated_at'])
    else:
        if stock.stock < quantity:
            raise ValueError(f"Insufficient POS stock ({stock.stock}) to dispose {quantity}.")
        stock.stock -= quantity
        stock.save(update_fields=['stock', 'updated_at'])

    if product.cost_method == 'FIFO':
        from apps.products.services.fifo_service import consume_fifo_lots
        write_off_value = consume_fifo_lots(product, quantity).quantize(Decimal('0.01'))
    else:
        write_off_value = (Decimal(quantity) * (product.cost_price or Decimal('0.00'))).quantize(Decimal('0.01'))

    entry = None
    if write_off_value > Decimal('0.00'):
        from apps.bookkeeping.models import get_inventory_account
        expense_acc = _get_or_create_account(company, _INVENTORY_WRITE_OFF_EXPENSE, 'EXPENSE', code='5910')
        entry = post_journal_entry(
            company=company, date=None,
            description=f'Inventory write-off — {product.name} ({quantity} units, {disposal_reason})',
            journal_type='PROVISION', source_type='STOCK_DISPOSAL', created_by=posted_by,
            lines=[
                {'account': expense_acc, 'entry_type': 'DEBIT', 'amount': write_off_value, 'narration': reason or disposal_reason},
                {'account': get_inventory_account(company), 'entry_type': 'CREDIT', 'amount': write_off_value,
                 'narration': f'Write-off of {product.name}'},
            ],
        )

    from .stock_ledger_service import log_movement
    stock_txn = log_movement(
        product, transaction_type='DISPOSAL', stock_type=stock_type, quantity=quantity,
        qty_change=-quantity, user=posted_by, reason=reason,
        unit_cost=write_off_value / Decimal(quantity),
        disposal_reason=disposal_reason, journal_entry=entry,
    )

    logger.info(
        'stock_disposal_posted product=%s qty=%s reason=%s value=%s journal=%s',
        product.id, quantity, disposal_reason, write_off_value, entry.id if entry else None,
    )
    return stock_txn
