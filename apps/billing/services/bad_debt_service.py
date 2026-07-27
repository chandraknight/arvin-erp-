"""
Bad debt write-off (NFRS 9) — records an invoice balance as uncollectible.

write_off_bad_debt(invoice, amount, reason, user)
  → posts DR Bad Debt Expense / CR the customer's AR sub-account,
    reduces the invoice's outstanding_balance, and locks it as WRITTEN_OFF.
"""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F


@transaction.atomic
def write_off_bad_debt(invoice, amount, reason, user):
    from apps.billing.models import Invoice, BadDebtWriteOff
    from apps.bookkeeping.models import post_journal_entry, get_or_create_system_account

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
    bad_debt_expense_acc = get_or_create_system_account(
        company, 'Bad Debt Expense', 'EXPENSE', code='5930'
    )

    journal_entry = post_journal_entry(
        company=company,
        date=invoice.transaction_date,
        description=f"Bad debt write-off — Invoice {invoice.invoice_number} ({reason[:100]})",
        lines=[
            {'account': bad_debt_expense_acc, 'entry_type': 'DEBIT', 'amount': amount,
             'narration': f'Write-off of Invoice {invoice.invoice_number}'},
            {'account': invoice.customer.related_ledger_account, 'entry_type': 'CREDIT', 'amount': amount,
             'narration': f'Write-off of Invoice {invoice.invoice_number}'},
        ],
        created_by=user,
        source_type='BAD_DEBT_WRITEOFF',
    )

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
