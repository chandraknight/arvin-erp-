"""
NFRS 2 (IAS 2) — Cost of Goods Sold posting at time of sale.

post_cogs_journal(company, invoice, cost_lines, posted_by)
  → posts DR Cost of Goods Sold / CR Inventory for the actual cost consumed
    by a sale, so the GL (not just the reporting overlay in
    apps/reports/views.py get_cogs_by_product) reflects real inventory
    movement and gross margin.

Journal entry:
  DR  Cost of Goods Sold     sum(cost_lines)
  CR  Inventory              sum(cost_lines)

Mirrors apps/products/services/stock_disposal_service.py's posting pattern.
"""
from __future__ import annotations

import logging
from decimal import Decimal

from django.db import transaction

logger = logging.getLogger(__name__)

_COGS_ACCOUNT = 'Cost of Goods Sold'
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
def post_cogs_journal(company, description: str, total_cost: Decimal, posted_by=None):
    """
    Post the COGS/Inventory journal entry for a sale.

    total_cost is the sum of actual cost consumed (FIFO lot cost, or
    qty * cost_price for non-FIFO products) — the caller is responsible for
    computing it via apps.products.services.fifo_service.consume_fifo_lots
    or the cost_price fallback, same as stock_disposal_service does.

    Returns the created JournalEntry, or None if total_cost is zero.
    """
    from apps.bookkeeping.models import JournalEntry, JournalEntryLine, assert_balanced

    total_cost = Decimal(total_cost).quantize(Decimal('0.01'))
    if total_cost <= Decimal('0.00'):
        return None

    cogs_acc = _get_or_create_account(company, _COGS_ACCOUNT, 'EXPENSE', code='5900')
    inventory_acc = _get_or_create_account(company, _INVENTORY_ACCOUNT, 'ASSET', code='1400')

    entry = JournalEntry.objects.create(
        company=company,
        description=description,
        journal_type='GENERAL',
        created_by=posted_by,
    )
    JournalEntryLine.objects.bulk_create([
        JournalEntryLine(
            journal_entry=entry, account=cogs_acc, entry_type='DEBIT',
            amount=total_cost, narration=description,
        ),
        JournalEntryLine(
            journal_entry=entry, account=inventory_acc, entry_type='CREDIT',
            amount=total_cost, narration=description,
        ),
    ])
    assert_balanced(entry)

    logger.info('cogs_posted company=%s value=%s journal=%s', company.id, total_cost, entry.id)
    return entry
