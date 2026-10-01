"""
Goods Received Not Invoiced (GRNI) — NFRS 2 perpetual inventory on purchase receipt.

Receipt (stock moves in):      DR Inventory / CR Goods Received Not Invoiced
Vendor bill (invoice arrives): DR Goods Received Not Invoiced / (VAT) / CR Accounts Payable

so stock reaches the ledger when it physically arrives, not only when the bill is
entered. If the bill was entered BEFORE the goods were received, the bill itself
capitalises Inventory and receipt posts nothing (see apps.billing.signals), so the
stock is never counted twice. The rule is stable on re-save because it keys off the
presence of a live GRN entry, not the order of events.
"""
from decimal import Decimal

GRNI_ACCOUNT_NAME = 'Goods Received Not Invoiced'
GRNI_ACCOUNT_CODE = '2105'


def _company(purchase_order):
    return purchase_order.company or purchase_order.vendor.company


def grn_description(purchase_order):
    return f"GRN {purchase_order.purchase_order_number}"


def get_grni_account(company):
    from apps.bookkeeping.models import get_or_create_system_account
    return get_or_create_system_account(
        company, GRNI_ACCOUNT_NAME, 'LIABILITY', code=GRNI_ACCOUNT_CODE, is_current=True,
    )


def has_live_grn(purchase_order):
    from apps.bookkeeping.models import JournalEntry
    return JournalEntry.objects.filter(
        company=_company(purchase_order), source_type='GRN',
        description=grn_description(purchase_order), is_reversed=False, is_deleted=False,
    ).exists()


def post_goods_received_journal(purchase_order, user=None):
    """
    Post DR Inventory / CR GRNI for the stock lines of a received PO.
    Returns the JournalEntry, or None when nothing should be posted (inventory
    disabled, no stock value, already posted, or a bill already capitalised it).
    """
    from apps.billing.models import VendorBill
    from apps.bookkeeping.models import post_journal_entry, get_inventory_account

    company = _company(purchase_order)
    if not company or not company.enable_inventory:
        return None
    if has_live_grn(purchase_order):
        return None
    if VendorBill.objects.filter(
        purchase_order=purchase_order, is_deleted=False,
    ).exclude(status='CANCELLED').exists():
        return None

    value = sum(
        (Decimal(item.quantity) * item.price
         for item in purchase_order.items.filter(item_type='STOCK', product__isnull=False)),
        Decimal('0.00'),
    ).quantize(Decimal('0.01'))
    if value <= 0:
        return None

    return post_journal_entry(
        company=company, date=None, description=grn_description(purchase_order),
        source_type='GRN', created_by=user,
        lines=[
            {'account': get_inventory_account(company), 'entry_type': 'DEBIT', 'amount': value,
             'narration': f'Goods received {purchase_order.purchase_order_number}'},
            {'account': get_grni_account(company), 'entry_type': 'CREDIT', 'amount': value,
             'narration': f'Goods received {purchase_order.purchase_order_number}'},
        ],
    )
