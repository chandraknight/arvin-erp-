from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import DatabaseError
import logging

from apps.billing.models import Invoice, CreditNote, DebitNote, VendorBill
from apps.bookkeeping.models import JournalEntry, JournalEntryLine, LedgerAccount, reverse_journal
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
def _note_tax_amount(instance):
    """
    Return the VAT portion for a credit/debit note.
    Uses instance.tax_amount if set; otherwise pro-rates from the linked invoice.
    Pro-rating: note_amount / invoice.total * invoice.tax_amount
    """
    from decimal import Decimal
    if instance.tax_amount and instance.tax_amount > 0:
        return instance.tax_amount
    inv = instance.invoice
    if inv and inv.total and inv.total > 0 and inv.tax_amount and inv.tax_amount > 0:
        return (instance.amount / inv.total * inv.tax_amount).quantize(Decimal('0.01'))
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
    sales_account = _get_ledger(instance.company, "Sales Revenue")
    tax_account = _get_ledger(instance.company, "Tax Payable")

    if not ar_account or not sales_account:
        logger.error(
            "Missing ledger accounts for credit note %s", instance.credit_note_number
        )
        return

    tax_amt = _note_tax_amount(instance)
    net_sales = instance.amount - tax_amt

    entry = JournalEntry.objects.create(
        company=instance.company,
        date=instance.invoice.transaction_date if instance.invoice else instance.created_at.date(),
        description=f"Credit Note {instance.credit_note_number}",
    )
    lines = [
        JournalEntryLine(journal_entry=entry, account=sales_account, entry_type="DEBIT",  amount=net_sales),
        JournalEntryLine(journal_entry=entry, account=ar_account,    entry_type="CREDIT", amount=instance.amount),
    ]
    # NFRS: reverse the VAT liability that was posted on the original invoice
    if tax_amt > 0 and tax_account:
        lines.insert(1, JournalEntryLine(
            journal_entry=entry, account=tax_account, entry_type="DEBIT", amount=tax_amt,
        ))
    elif tax_amt > 0:
        logger.warning(
            "Tax Payable account not found — credit note %s VAT leg omitted",
            instance.credit_note_number,
        )
    JournalEntryLine.objects.bulk_create(lines)
    instance.journal_entry = entry
    instance.save(update_fields=["journal_entry"])

    audit_logger.info(
        "CREDIT_NOTE_APPLIED credit_note=%s journal_entry=%s company=%s tax_amt=%s",
        instance.credit_note_number, entry.id, instance.company_id, tax_amt,
    )


# ─────────────────────────────────────────────────────────────────────────────
# DEBIT NOTE — fixed: removed the early-exit guard that prevented re-creation
# ─────────────────────────────────────────────────────────────────────────────
@receiver(post_save, sender=DebitNote)
def create_journal_entry_for_debit_note(sender, instance, created, **kwargs):
    if instance.status != StatusChoicesEnum.Applied.value:
        return

    # Reverse and recreate — accounting records are immutable
    for old_entry in JournalEntry.objects.filter(debit_note=instance, is_reversed=False):
        reverse_journal(old_entry, reason=f'Debit note {instance.debit_note_number} re-applied')
    setup_default_ledger_accounts(instance.company)

    if instance.customer and instance.customer.related_ledger_account:
        ar_account = instance.customer.related_ledger_account
    else:
        ar_account = _get_ledger(instance.company, "Accounts Receivable")
    sales_account = _get_ledger(instance.company, "Sales Revenue")
    tax_account = _get_ledger(instance.company, "Tax Payable")

    if not ar_account or not sales_account:
        logger.error(
            "Missing ledger accounts for debit note %s", instance.debit_note_number
        )
        return

    tax_amt = _note_tax_amount(instance)
    net_sales = instance.amount - tax_amt

    entry = JournalEntry.objects.create(
        company=instance.company,
        date=instance.invoice.transaction_date if instance.invoice else instance.created_at.date(),
        description=f"Debit Note {instance.debit_note_number}",
    )
    lines = [
        JournalEntryLine(journal_entry=entry, account=ar_account,    entry_type="DEBIT",  amount=instance.amount),
        JournalEntryLine(journal_entry=entry, account=sales_account, entry_type="CREDIT", amount=net_sales),
    ]
    # NFRS: record the additional VAT liability on the debit note
    if tax_amt > 0 and tax_account:
        lines.append(JournalEntryLine(
            journal_entry=entry, account=tax_account, entry_type="CREDIT", amount=tax_amt,
        ))
    elif tax_amt > 0:
        logger.warning(
            "Tax Payable account not found — debit note %s VAT leg omitted",
            instance.debit_note_number,
        )
    JournalEntryLine.objects.bulk_create(lines)
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
    entry = JournalEntry.objects.create(
        company=company,
        date=instance.bill_date or tz_now().date(),
        description=f"Vendor Bill {instance.bill_number}",
    )

    lines = []
    from decimal import Decimal
    items_subtotal = Decimal("0.00")
    for item in instance.items.all():
        debit_account = item.debit_account or _get_ledger(company, "Purchase Expense")
        if not debit_account:
            continue
        lines.append(JournalEntryLine(
            journal_entry=entry,
            account=debit_account,
            entry_type="DEBIT",
            amount=item.total_price,
        ))
        items_subtotal += item.total_price

    if not lines:
        # Soft-delete the empty shell entry — no lines means nothing to post
        entry.is_deleted = True
        entry.save(update_fields=['is_deleted'])
        return

    # ── VAT leg: when vendor charged VAT, debit Input VAT (recoverable asset) ──
    tax_amount = Decimal(str(instance.tax_amount or "0.00"))
    if tax_amount > Decimal("0.00"):
        input_vat_account = _get_ledger(company, "Input VAT")
        if input_vat_account:
            lines.append(JournalEntryLine(
                journal_entry=entry,
                account=input_vat_account,
                entry_type="DEBIT",
                amount=tax_amount,
            ))
        else:
            # Fallback: no Input VAT account yet — warn but don't block
            logger.warning(
                "No 'Input VAT' ledger account for company %s — VAT of %s on vendor bill %s "
                "will not be journalised. Create the account to fix this.",
                company, tax_amount, instance.bill_number,
            )
            # Still include the tax in AP so the books at least balance
            # (will appear as part of Purchase Expense implicitly)

    # AP CREDIT = full payable amount to vendor (items subtotal + VAT)
    ap_total = items_subtotal + tax_amount
    lines.append(JournalEntryLine(
        journal_entry=entry,
        account=ap_account,
        entry_type="CREDIT",
        amount=ap_total,
    ))
    JournalEntryLine.objects.bulk_create(lines)
