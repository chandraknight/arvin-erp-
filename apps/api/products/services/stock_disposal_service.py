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
    from apps.bookkeeping.models import JournalEntry, JournalEntryLine, assert_balanced

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

    write_off_value = (Decimal(quantity) * (product.cost_price or Decimal('0.00'))).quantize(Decimal('0.01'))

    entry = None
    if write_off_value > Decimal('0.00'):
        expense_acc = _get_or_create_account(company, _INVENTORY_WRITE_OFF_EXPENSE, 'EXPENSE', code='5910')
        inventory_acc = _get_or_create_account(company, _INVENTORY_ACCOUNT, 'ASSET', code='1400')

        entry = JournalEntry.objects.create(
            company=company,
            description=f'Inventory write-off — {product.name} ({quantity} units, {disposal_reason})',
            journal_type='PROVISION',
            created_by=posted_by,
        )
        JournalEntryLine.objects.bulk_create([
            JournalEntryLine(
                journal_entry=entry, account=expense_acc, entry_type='DEBIT',
                amount=write_off_value, narration=reason or disposal_reason,
            ),
            JournalEntryLine(
                journal_entry=entry, account=inventory_acc, entry_type='CREDIT',
                amount=write_off_value, narration=f'Write-off of {product.name}',
            ),
        ])
        assert_balanced(entry)

    stock_txn = StockTransaction.objects.create(
        product=product,
        user=posted_by,
        transaction_type='DISPOSAL',
        stock_type=stock_type,
        quantity=quantity,
        reason=reason,
        disposal_reason=disposal_reason,
        journal_entry=entry,
    )

    logger.info(
        'stock_disposal_posted product=%s qty=%s reason=%s value=%s journal=%s',
        product.id, quantity, disposal_reason, write_off_value, entry.id if entry else None,
    )
    return stock_txn
