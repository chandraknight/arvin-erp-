from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import DatabaseError
import logging

from apps.billing.models import Invoice, CreditNote, DebitNote, VendorBill
from apps.bookkeeping.models import JournalEntry, LedgerAccount, reverse_journal, post_journal_entry
from apps.company.services.company_services import setup_default_ledger_accounts
from apps.utils.constant import StatusChoicesEnum

logger = logging.getLogger(__name__)
audit_logger = logging.getLogger("audit")


def _get_ledger(company, account_name):
    return LedgerAccount.objects.filter(company=company, name=account_name).first()


# ─────────────────────────────────────────────────────────────────────────────
# INVOICE — delegates to fn_post_invoice_journal (PostgreSQL)
# Fixes: Bug 2 (transaction_date), Bug 4 (exact description match)
# ─────────────────────────────────────────────────────────────────────────────
@receiver(post_save, sender=Invoice)
def create_journal_entry_for_invoice(sender, instance, created, **kwargs):
    # Create view sets this flag and calls post_invoice_journal explicitly once
    # with the final, correct totals after all items are saved.
    if getattr(instance, '_skip_journal', False):
        return
    if not instance.invoice_number:
        return
    if not instance.total or instance.total <= 0:
        return
    if instance.status == 'ESTIMATE':
        return

    setup_default_ledger_accounts(instance.company)

    try:
        from apps.bookkeeping.db_functions import post_invoice_journal
        post_invoice_journal(instance.id)
    except DatabaseError as exc:
        logger.error(
            "post_invoice_journal failed invoice=%s error=%s",
            instance.invoice_number, exc,
        )
        raise exc


# ─────────────────────────────────────────────────────────────────────────────
# CREDIT NOTE
# ─────────────────────────────────────────────────────────────────────────────
def _note_tax_amount(instance, source=None, source_total=None):
    """
    VAT portion for a credit/debit note. Uses instance.tax_amount if set;
    otherwise pro-rates from the source document:
    note_amount / source_total * source.tax_amount
    """
    from decimal import Decimal
    if instance.tax_amount and instance.tax_amount > 0:
        return instance.tax_amount
    if source is None:
        source = instance.invoice
        source_total = source.total if source else None
    if source and source_total and source_total > 0 and source.tax_amount and source.tax_amount > 0:
        return (instance.amount / source_total * source.tax_amount).quantize(Decimal('0.01'))
    return Decimal('0.00')


@receiver(post_save, sender=CreditNote)
def create_journal_entry_for_credit_note(sender, instance, created, **kwargs):
    if instance.status != StatusChoicesEnum.Applied.value:
        return

    # Reverse existing entry instead of deleting — accounting records are immutable
    for old_entry in JournalEntry.objects.filter(credit_note=instance, is_reversed=False):
        reverse_journal(old_entry, reason=f'Credit note {instance.credit_note_number} re-applied')
    setup_default_ledger_accounts(instance.company)

    if instance.customer and instance.customer.related_ledger_account:
        ar_account = instance.customer.related_ledger_account
    else:
        ar_account = _get_ledger(instance.company, "Accounts Receivable")
    # NFRS presentation: sales returns hit the contra-revenue account, not gross revenue
    sales_returns_account = (
        _get_ledger(instance.company, "Sales Returns")
        or _get_ledger(instance.company, "Sales Revenue")
    )
    tax_account = _get_ledger(instance.company, "Tax Payable")

    if not ar_account or not sales_returns_account:
        logger.error(
            "Missing ledger accounts for credit note %s", instance.credit_note_number
        )
        return

    tax_amt = _note_tax_amount(instance)
    # NFRS: reverse the VAT liability posted on the original invoice. If there's
    # no Tax Payable account to receive that leg, the VAT amount must stay on
    # the sales-returns debit instead of vanishing — otherwise the CREDIT side
    # (always the full instance.amount) would exceed the DEBIT side.
    if tax_amt > 0 and not tax_account:
        logger.warning(
            "Tax Payable account not found — credit note %s VAT folded into sales returns",
            instance.credit_note_number,
        )
    lines = []
    if tax_amt > 0 and tax_account:
        lines.append({'account': sales_returns_account, 'entry_type': 'DEBIT', 'amount': instance.amount - tax_amt})
        lines.append({'account': tax_account, 'entry_type': 'DEBIT', 'amount': tax_amt})
    else:
        lines.append({'account': sales_returns_account, 'entry_type': 'DEBIT', 'amount': instance.amount})
    lines.append({'account': ar_account, 'entry_type': 'CREDIT', 'amount': instance.amount})

    entry = post_journal_entry(
        company=instance.company,
        date=instance.invoice.transaction_date if instance.invoice else instance.created_at.date(),
        description=f"Credit Note {instance.credit_note_number}",
        lines=lines,
        source_type='CREDIT_NOTE',
    )
    instance.journal_entry = entry
    instance.save(update_fields=["journal_entry"])

    audit_logger.info(
        "CREDIT_NOTE_APPLIED credit_note=%s journal_entry=%s company=%s tax_amt=%s",
        instance.credit_note_number, entry.id, instance.company_id, tax_amt,
    )


# ─────────────────────────────────────────────────────────────────────────────
# DEBIT NOTE — purchase return: DR Accounts Payable, CR Purchase Returns + Input VAT
# ─────────────────────────────────────────────────────────────────────────────
@receiver(post_save, sender=DebitNote)
def create_journal_entry_for_debit_note(sender, instance, created, **kwargs):
    if instance.status != StatusChoicesEnum.Applied.value:
        return

    # Reverse and recreate — accounting records are immutable
    for old_entry in JournalEntry.objects.filter(debit_note=instance, is_reversed=False):
        reverse_journal(old_entry, reason=f'Debit note {instance.debit_note_number} re-applied')
    setup_default_ledger_accounts(instance.company)

    ap_account = _get_ledger(instance.company, "Accounts Payable")
    purchase_returns_account = (
        _get_ledger(instance.company, "Purchase Returns")
        or _get_ledger(instance.company, "Purchase Expense")
    )
    input_vat_account = _get_ledger(instance.company, "Input VAT")

    if not ap_account or not purchase_returns_account:
        logger.error(
            "Missing ledger accounts for debit note %s", instance.debit_note_number
        )
        return

    bill = instance.vendor_bill
    tax_amt = _note_tax_amount(instance, source=bill, source_total=bill.total_amount if bill else None)

    # NFRS: returning goods surrenders the recoverable Input VAT claimed on the
    # bill. If there's no Input VAT account to receive that leg, the amount
    # must stay on the purchase-returns credit instead of vanishing —
    # otherwise the DEBIT side (always the full instance.amount) would exceed
    # the CREDIT side.
    if tax_amt > 0 and not input_vat_account:
        logger.warning(
            "Input VAT account not found — debit note %s VAT folded into purchase returns",
            instance.debit_note_number,
        )
    lines = [
        {'account': ap_account, 'entry_type': 'DEBIT', 'amount': instance.amount},
    ]
    if tax_amt > 0 and input_vat_account:
        lines.append({'account': purchase_returns_account, 'entry_type': 'CREDIT', 'amount': instance.amount - tax_amt})
        lines.append({'account': input_vat_account, 'entry_type': 'CREDIT', 'amount': tax_amt})
    else:
        lines.append({'account': purchase_returns_account, 'entry_type': 'CREDIT', 'amount': instance.amount})

    entry = post_journal_entry(
        company=instance.company,
        date=bill.bill_date if bill else instance.created_at.date(),
        description=f"Debit Note {instance.debit_note_number}",
        lines=lines,
        source_type='DEBIT_NOTE',
    )
    instance.journal_entry = entry
    instance.save(update_fields=["journal_entry"])

    audit_logger.info(
        "DEBIT_NOTE_APPLIED debit_note=%s journal_entry=%s company=%s tax_amt=%s",
        instance.debit_note_number, entry.id, instance.company_id, tax_amt,
    )


# ─────────────────────────────────────────────────────────────────────────────
# VENDOR BILL
# ─────────────────────────────────────────────────────────────────────────────
@receiver(post_save, sender=VendorBill)
def create_journal_entry_for_vendor_bill(sender, instance, created, **kwargs):
    # Caller sets this flag on non-financial saves (initial save before items exist)
    if getattr(instance, '_skip_journal', False):
        return
    if not instance.bill_number:
        return
    # Only re-journal when financially meaningful fields are involved.
    # Saves with update_fields=['status'] or ['is_deleted'] must not create entries.
    update_fields = kwargs.get('update_fields')
    if update_fields is not None and not {
        'total_amount', 'tax_amount', 'tax_percent', 'bill_date', 'bill_number'
    }.intersection(set(update_fields)):
        return

    company = (
        instance.purchase_order.company
        if instance.purchase_order
        else instance.vendor.company
    )
    setup_default_ledger_accounts(company)

    # Reverse previous non-deleted entries — accounting records are immutable.
    # Exclude soft-deleted shells (empty bills with no lines) to avoid phantom reversals.
    for old_entry in JournalEntry.objects.filter(
        company=company,
        description=f"Vendor Bill {instance.bill_number}",
        is_reversed=False,
        is_deleted=False,
    ):
        reverse_journal(old_entry, reason=f'Vendor bill {instance.bill_number} re-saved')

    ap_account = _get_ledger(company, "Accounts Payable")
    if not ap_account:
        logger.error(
            "No Accounts Payable account for company %s — vendor bill %s not journalised",
            company, instance.bill_number,
        )
        return

    from django.utils.timezone import now as tz_now
    from decimal import Decimal

    lines = []
    items_subtotal = Decimal("0.00")
    fallback_expense_account = None
    for item in instance.items.all():
        debit_account = item.debit_account or _get_ledger(company, "Purchase Expense")
        if not debit_account:
            continue
        lines.append({'account': debit_account, 'entry_type': 'DEBIT', 'amount': item.total_price})
        items_subtotal += item.total_price
        fallback_expense_account = fallback_expense_account or debit_account

    if not lines:
        # No lines means nothing to post — no entry created, nothing to clean up.
        return

    # ── VAT leg: when vendor charged VAT, debit Input VAT (recoverable asset) ──
    tax_amount = Decimal(str(instance.tax_amount or "0.00"))
    if tax_amount > Decimal("0.00"):
        input_vat_account = _get_ledger(company, "Input VAT")
        if input_vat_account:
            lines.append({'account': input_vat_account, 'entry_type': 'DEBIT', 'amount': tax_amount})
        else:
            # No Input VAT account yet — fold the tax into the expense leg
            # instead of dropping it, so the entry still balances against the
            # AP credit below (which always includes the full tax-inclusive total).
            logger.warning(
                "No 'Input VAT' ledger account for company %s — VAT of %s on vendor bill %s "
                "folded into Purchase Expense. Create the account to track it separately.",
                company, tax_amount, instance.bill_number,
            )
            lines.append({'account': fallback_expense_account, 'entry_type': 'DEBIT', 'amount': tax_amount})

    # AP CREDIT = full payable amount to vendor (items subtotal + VAT)
    ap_total = items_subtotal + tax_amount
    lines.append({'account': ap_account, 'entry_type': 'CREDIT', 'amount': ap_total})

    post_journal_entry(
        company=company,
        date=instance.bill_date or tz_now().date(),
        description=f"Vendor Bill {instance.bill_number}",
        lines=lines,
        source_type='VENDOR_BILL',
    )
