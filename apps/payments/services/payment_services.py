from django.db import IntegrityError
from django.db.models import F
from decimal import Decimal
from django.utils import timezone
import logging

from apps.bookkeeping.models import LedgerAccount, JournalEntry, JournalEntryLine
from apps.payments.models import Payment
from .payment_number_service import generate_payment_number

logger = logging.getLogger(__name__)


def handle_customer_payment_journal(instance):
    """Create journal entry for customer payment."""
    ar_account = LedgerAccount.objects.filter(company=instance.company, name="Accounts Receivable").first()
    if not ar_account:
        raise ValueError(f"Ledger account 'Accounts Receivable' not found for company {instance.company}. Run company setup first.")
    bank_or_cash_account = get_payment_account(instance.company, instance.method)

    entry = JournalEntry.objects.create(
        company=instance.company,
        date=instance.date,
        description=f"Payment for Invoice {instance.invoice.invoice_number}"
    )

    JournalEntryLine.objects.bulk_create([
        JournalEntryLine(journal_entry=entry, account=bank_or_cash_account, entry_type="DEBIT", amount=instance.amount),
        JournalEntryLine(journal_entry=entry, account=ar_account, entry_type="CREDIT", amount=instance.amount),
    ])

    instance.journal_entry = entry
    instance.amount_applied = instance.amount
    instance.save(update_fields=["journal_entry", "amount_applied"])


def handle_other_payment_journal(instance):
    """Create journal entry for non-customer payments."""
    if not instance.company:
        return
    
    setup_default_ledger_accounts(instance.company)

    if instance.payment_type == 'VENDOR':
        target_account_name = "Accounts Payable"
        description = "Payment to Vendor"
    elif instance.payment_type == 'EXPENSE':
        if not instance.ledger_account:
            raise ValueError("EXPENSE payment requires a ledger_account to be set.")
        target_account_name = instance.ledger_account.name
        description = "Expense Payment"
    elif instance.payment_type == 'SALARY':
        target_account_name = "Salary Expense"
        description = "Salary Payment"
    else:  # Handle OTHER payments
        target_account_name = instance.ledger_account.name if instance.ledger_account else "Miscellaneous Expense"
        description = "Other Payment"

    destination_account = LedgerAccount.objects.filter(company=instance.company, name=target_account_name).first()
    if not destination_account:
        raise ValueError(f"Ledger account '{target_account_name}' not found for company {instance.company}. Run company setup first.")
    source_account = get_payment_account(instance.company, instance.method)

    entry = JournalEntry.objects.create(
        company=instance.company,
        date=instance.date,
        description=description
    )

    # SALARY: DR expense/payable account, CR cash/bank (paying out money)
    # VENDOR/EXPENSE/OTHER: DR expense account, CR cash/bank (same direction)
    JournalEntryLine.objects.bulk_create([
        JournalEntryLine(journal_entry=entry, account=destination_account, entry_type="DEBIT", amount=instance.amount),
        JournalEntryLine(journal_entry=entry, account=source_account, entry_type="CREDIT", amount=instance.amount),
    ])

    instance.journal_entry = entry
    instance.amount_applied = instance.amount
    instance.save(update_fields=["journal_entry", "amount_applied"])


def create_invoice_payment(
    request, invoice, payment_method, payment_amount,
    payment_reference=None, payment_description=None, payment_destination=None,
    payment_date=None,
):
    """
    Create a payment for an invoice with validation and retry logic.

    Args:
        payment_date: Optional AD date object. Defaults to today.

    Returns:
        (success: bool, payment: Payment | None, error: str | None)
    """
    # Validate
    if not invoice.company:
        return False, None, "Invoice has no company assigned"
    if not invoice.invoice_number:
        return False, None, "Invoice has no invoice number assigned"

    payment_amount = Decimal(str(payment_amount))
    if payment_amount <= 0:
        return False, None, "Payment amount must be greater than zero"

    # Refresh invoice from DB to get the latest total/outstanding_balance
    # (avoids stale in-memory values when called right after invoice creation)
    invoice.refresh_from_db()

    if payment_amount > invoice.total:
        return False, None, (
            f"Payment amount ({payment_amount}) exceeds invoice total ({invoice.total})"
        )

    # Resolve payment date — fall back to today
    resolved_date = payment_date if payment_date is not None else timezone.now().date()

    # Generate payment reference number
    reference_number = payment_reference or None
    sequence_number = None
    payment_fiscal_year = None
    if not reference_number:
        try:
            reference_number, sequence_number, payment_fiscal_year = generate_payment_number(invoice.company.id, 'CUSTOMER')
        except Exception as e:
            logger.warning(f"Could not generate payment number: {e}")

    # Create payment with retry for transient integrity errors
    for attempt in range(3):
        try:
            payment = Payment(
                company=invoice.company,
                branch=invoice.branch,
                invoice=invoice,
                date=resolved_date,
                amount=payment_amount,
                discount_amount=getattr(invoice, 'discount_amount', Decimal('0.00')),
                method=payment_method,
                payment_type='CUSTOMER',
                reference_number=reference_number,
                sequence_number=sequence_number,
                fiscal_year=payment_fiscal_year,
                description=payment_description,
                created_by=getattr(request, 'user', None),
            )
            payment.save()

            # Use a raw queryset UPDATE so Django's post_save signal is NOT fired
            # on the invoice again. Firing post_save here would re-run
            # post_invoice_journal inside the same transaction, which can DELETE
            # the newly-created journal entry before its FK lines are committed.
            from apps.billing.models import Invoice as InvoiceModel
            new_outstanding = max(Decimal('0'), invoice.total - payment_amount)
            InvoiceModel.objects.filter(pk=invoice.pk).update(
                outstanding_balance=new_outstanding
            )
            invoice.outstanding_balance = new_outstanding

            logger.info(
                "Payment %s created for invoice %s — amount %s outstanding now %s",
                payment.pk, invoice.invoice_number, payment_amount, new_outstanding,
            )
            return True, payment, None

        except IntegrityError as e:
            err = str(e)
            if 'Duplicate payment' in err:
                return False, None, "A payment with the same details already exists for this invoice."
            if attempt < 2:
                logger.warning(f"IntegrityError attempt {attempt + 1}: {e}")
                continue
            return False, None, f"Database integrity error: {err}"

        except Exception as e:
            if attempt < 2:
                logger.warning(f"Payment creation attempt {attempt + 1} failed: {e}")
                continue
            logger.error(f"Payment creation failed after 3 attempts: {e}")
            return False, None, str(e)

    return False, None, "Payment creation failed after retries"


def consolidate_split_payment_journals(payments):
    """
    Merge the individual journal entries created for a list of split-payment
    Payment objects into a single journal entry on the first payment.

    Background: each Payment.save() fires a signal that creates its own
    JournalEntry via post_payment_journal().  When the same invoice is paid
    with multiple methods in one go we want ONE combined entry in the ledger.

    Strategy (safe with the existing OneToOneField):
    - Take the first payment's JournalEntry as the canonical entry.
    - For every other payment: move its JournalEntryLine rows into the
      canonical entry, null out the OneToOne FK so the entry can be deleted,
      then delete the now-empty entry.
    """
    payments = [p for p in payments if p and getattr(p, 'journal_entry_id', None)]
    if len(payments) <= 1:
        return

    from apps.bookkeeping.models import JournalEntryLine

    primary = payments[0]
    primary_entry = primary.journal_entry

    for payment in payments[1:]:
        extra_entry = payment.journal_entry
        if not extra_entry:
            continue
        # Re-point all lines to the canonical entry
        JournalEntryLine.objects.filter(journal_entry=extra_entry).update(
            journal_entry=primary_entry
        )
        # Detach the OneToOne link and soft-delete the now-empty duplicate entry
        Payment.objects.filter(pk=payment.pk).update(journal_entry=None)
        extra_entry.is_deleted = True
        extra_entry.save(update_fields=['is_deleted'])

    primary_entry.refresh_from_db()
