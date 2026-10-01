"""
NFRS 2 — true the ledger Inventory control account up to the stock valuation.

Under the perpetual method Inventory is debited on purchase and credited on
sale/write-off. Stock bought before that method was adopted (or receipts that
were expensed) never reached the account, so the ledger and the stock
valuation disagree. This posts the one-off difference:

  ledger > valuation  (write-down):  DR Cost of Goods Sold / CR Inventory
  ledger < valuation  (capitalise):  DR Inventory / CR Cost of Goods Sold

Used by the Closing Stock report action and by `manage.py reconcile_inventory`.
"""
from decimal import Decimal


def inventory_reconciliation_preview(company, as_of):
    """Return (book_value, valuation, adjustment) without posting anything."""
    from apps.products.services.valuation_service import compute_stock_valuation
    from apps.reports.views import get_inventory_ledger_balance

    _, totals = compute_stock_valuation(company)
    valuation = totals['total_carrying_value']
    book_value = get_inventory_ledger_balance(company, as_of)
    return book_value, valuation, (book_value - valuation).quantize(Decimal('0.01'))


def reconcile_inventory(company, as_of, user=None):
    """
    Post the true-up entry dated `as_of`. Returns the JournalEntry, or None if the
    ledger already agrees. Raises ValueError if one was already posted for that date.
    """
    from apps.bookkeeping.models import (
        JournalEntry, post_journal_entry, get_inventory_account, get_cogs_account,
    )

    if JournalEntry.objects.filter(
        company=company, source_type='CLOSING_STOCK', date=as_of, is_deleted=False,
    ).exists():
        raise ValueError(f"Closing stock has already been posted for period ending {as_of}.")

    book_value, valuation, adjustment = inventory_reconciliation_preview(company, as_of)
    if adjustment == Decimal('0.00'):
        return None

    inventory_acc = get_inventory_account(company)
    cogs_acc = get_cogs_account(company)
    write_down = adjustment > 0
    amount = abs(adjustment)
    return post_journal_entry(
        company=company, date=as_of, created_by=user, source_type='CLOSING_STOCK',
        description=f"Closing stock adjustment — period ending {as_of} (lower of cost or NRV)",
        lines=[
            {'account': cogs_acc if write_down else inventory_acc, 'entry_type': 'DEBIT',
             'amount': amount, 'narration': f'Ledger {book_value} vs valuation {valuation}'},
            {'account': inventory_acc if write_down else cogs_acc, 'entry_type': 'CREDIT',
             'amount': amount, 'narration': f'Ledger {book_value} vs valuation {valuation}'},
        ],
    )
