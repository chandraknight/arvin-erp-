"""
Bad debt write-off (NFRS 9) — records an invoice balance as uncollectible.

write_off_bad_debt(invoice, amount, reason, user)
  → posts DR Bad Debt Expense (net of VAT) + DR Tax Payable (VAT relief,
    Nepal VAT Act allows reclaiming output VAT on written-off bad debts) /
    CR the customer's AR sub-account for the full amount, reduces the
    invoice's outstanding_balance, and locks it as WRITTEN_OFF.
"""
import logging
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F

logger = logging.getLogger(__name__)


def _get_or_create_account(company, name, account_type, code=None):
    from apps.bookkeeping.models import LedgerAccount
    acc, _ = LedgerAccount.objects.get_or_create(
        company=company,
        name=name,
        defaults={
            'account_type': account_type,
            'code': code,
            'system_created': True,
            'is_current': account_type not in ('ASSET',),
        },
    )
    return acc


@transaction.atomic
def write_off_bad_debt(invoice, amount, reason, user):
    from apps.billing.models import Invoice, BadDebtWriteOff
    from apps.bookkeeping.models import JournalEntry, JournalEntryLine, assert_balanced

    if invoice.is_written_off:
        raise ValidationError("This invoice has already been written off.")
    if amount <= 0:
        raise ValidationError("Write-off amount must be greater than zero.")
    if amount > invoice.outstanding_balance:
        raise ValidationError(
            f"Write-off amount ({amount}) cannot exceed the outstanding balance ({invoice.outstanding_balance})."
        )
    if not reason or not reason.strip():
        raise ValidationError("A reason is required to write off a bad debt.")
    if not invoice.customer or not invoice.customer.related_ledger_account:
        raise ValidationError("Invoice has no linked customer receivable account to credit.")

    company = invoice.company
    bad_debt_expense_acc = _get_or_create_account(
        company, 'Bad Debt Expense', 'EXPENSE', code='5930'
    )

    # Nepal VAT Act: output VAT already remitted on an uncollected sale can be
    # reclaimed proportionally to the amount written off.
    vat_portion = Decimal('0.00')
    if invoice.tax_amount and invoice.total and invoice.total > 0:
        vat_portion = (amount * invoice.tax_amount / invoice.total).quantize(Decimal('0.01'))
    expense_portion = amount - vat_portion

    tax_payable_acc = None
    if vat_portion > 0:
        from apps.bookkeeping.models import LedgerAccount
        tax_payable_acc = LedgerAccount.objects.filter(company=company, name='Tax Payable').first()
        if not tax_payable_acc:
            logger.warning(
                "Tax Payable account not found for company %s — bad debt write-off for "
                "invoice %s posted without VAT relief leg. Needs manual accountant review.",
                company, invoice.invoice_number,
            )
            expense_portion = amount
            vat_portion = Decimal('0.00')

    journal_entry = JournalEntry.objects.create(
        company=company,
        date=invoice.transaction_date,
        description=f"Bad debt write-off — Invoice {invoice.invoice_number} ({reason[:100]})",
        created_by=user,
        journal_type='PROVISION',
    )
    JournalEntryLine.objects.create(
        journal_entry=journal_entry, account=bad_debt_expense_acc, entry_type='DEBIT',
        amount=expense_portion, narration=f'Write-off of Invoice {invoice.invoice_number}',
    )
    if vat_portion > 0 and tax_payable_acc:
        JournalEntryLine.objects.create(
            journal_entry=journal_entry, account=tax_payable_acc, entry_type='DEBIT',
            amount=vat_portion, narration=f'VAT relief on write-off of Invoice {invoice.invoice_number}',
        )
    JournalEntryLine.objects.create(
        journal_entry=journal_entry, account=invoice.customer.related_ledger_account, entry_type='CREDIT',
        amount=amount, narration=f'Write-off of Invoice {invoice.invoice_number}',
    )
    assert_balanced(journal_entry)

    Invoice.objects.filter(pk=invoice.pk).update(
        outstanding_balance=F('outstanding_balance') - amount,
        status='WRITTEN_OFF',
    )

    return BadDebtWriteOff.objects.create(
        invoice=invoice,
        amount=amount,
        reason=reason,
        written_off_by=user,
        journal_entry=journal_entry,
    )
