"""
Item-wise drill-down for Trial Balance / Balance Sheet / P&L account rows.

get_account_transactions() works for any LedgerAccount — the underlying
JournalEntryLine postings that make up its balance in the period.

get_product_breakdown() only returns something for accounts that map to
products (Sales Revenue, Purchase Expense, Cost of Goods Sold, Closing Stock)
— there is no FK chain from JournalEntry back to Invoice/VendorBill, so this
queries InvoiceItem/VendorBillItem/stock valuation independently, by date
range, the same way apps/reports/views.py's cogs_report already does. Any
other account (rent, salary, misc. expense, ...) has no product concept and
gets None — only the transaction-level drill-down applies to it.
"""
from decimal import Decimal

from django.db.models import Sum, F, ExpressionWrapper, DecimalField, Count

PURCHASE_ACCOUNT_NAMES = {'Purchase Expense', 'Purchases'}
COGS_ACCOUNT_NAMES = {'Cost of Goods Sold', 'COGS'}
CLOSING_STOCK_ACCOUNT_NAMES = {'Closing Stock', 'Inventory'}


def get_account_transactions(account, date_from=None, date_to=None):
    """The JournalEntryLine rows behind an account's balance in the period."""
    from apps.bookkeeping.models import JournalEntryLine

    qs = JournalEntryLine.objects.filter(
        account=account, journal_entry__is_deleted=False,
    ).select_related('journal_entry').order_by('journal_entry__date', 'journal_entry__created_at')
    if date_from:
        qs = qs.filter(journal_entry__date__gte=date_from)
    if date_to:
        qs = qs.filter(journal_entry__date__lte=date_to)
    return qs


def get_product_breakdown(account, company, date_from=None, date_to=None):
    """Per-product rows for accounts that map to products, else None."""
    name = account.name

    if account.account_type == 'REVENUE':
        return _sales_breakdown(company, date_from, date_to)
    if name in PURCHASE_ACCOUNT_NAMES:
        return _purchase_breakdown(company, date_from, date_to)
    if name in COGS_ACCOUNT_NAMES:
        return _cogs_breakdown(company, date_from, date_to)
    if name in CLOSING_STOCK_ACCOUNT_NAMES:
        return _closing_stock_breakdown(company)
    return None


def _sales_breakdown(company, date_from, date_to):
    from apps.billing.models import InvoiceItem

    qs = InvoiceItem.objects.filter(
        invoice__company=company, product__isnull=False,
    )
    if date_from:
        qs = qs.filter(invoice__transaction_date__gte=date_from)
    if date_to:
        qs = qs.filter(invoice__transaction_date__lte=date_to)

    rows = qs.values('product__id', 'product__name').annotate(
        qty=Sum('quantity'),
        amount=Sum(ExpressionWrapper(F('quantity') * F('price'), output_field=DecimalField())),
    ).order_by('-amount')
    return [{'product_name': r['product__name'], 'qty': r['qty'], 'amount': r['amount']} for r in rows]


def _purchase_breakdown(company, date_from, date_to):
    from apps.billing.models import VendorBillItem

    qs = VendorBillItem.objects.filter(
        vendor_bill__company=company, product__isnull=False,
    )
    if date_from:
        qs = qs.filter(vendor_bill__bill_date__gte=date_from)
    if date_to:
        qs = qs.filter(vendor_bill__bill_date__lte=date_to)

    rows = qs.values('product__id', 'product__name').annotate(
        qty=Sum('quantity'),
        amount=Sum(ExpressionWrapper(F('quantity') * F('price'), output_field=DecimalField())),
    ).order_by('-amount')
    return [{'product_name': r['product__name'], 'qty': r['qty'], 'amount': r['amount']} for r in rows]


def _cogs_breakdown(company, date_from, date_to):
    from apps.billing.models import InvoiceItem

    qs = InvoiceItem.objects.filter(
        invoice__company=company, product__isnull=False,
    )
    if date_from:
        qs = qs.filter(invoice__transaction_date__gte=date_from)
    if date_to:
        qs = qs.filter(invoice__transaction_date__lte=date_to)

    rows = qs.values('product__id', 'product__name').annotate(
        qty=Sum('quantity'),
        amount=Sum(ExpressionWrapper(F('quantity') * F('product__cost_price'), output_field=DecimalField())),
    ).order_by('-amount')
    return [{'product_name': r['product__name'], 'qty': r['qty'], 'amount': r['amount']} for r in rows]


def _closing_stock_breakdown(company):
    from apps.products.services.valuation_service import compute_stock_valuation

    rows, _totals = compute_stock_valuation(company)
    return [{
        'product_name': r['product'].name,
        'qty': r['qty'],
        'amount': r['carrying_value'],
    } for r in rows]
