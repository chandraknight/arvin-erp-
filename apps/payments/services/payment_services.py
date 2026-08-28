from django.db import IntegrityError
from decimal import Decimal
from django.utils import timezone
import logging

from apps.payments.models import Payment
from .payment_number_service import generate_payment_number

logger = logging.getLogger(__name__)


def create_invoice_payment(
    request, invoice, payment_method, payment_amount,
    payment_reference=None, payment_description=None, payment_destination=None,
    payment_date=None, bank_account=None,
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

    current_outstanding = invoice.outstanding_balance
    if current_outstanding is None:
        current_outstanding = invoice.total

    if payment_amount > current_outstanding:
        return False, None, (
            f"Payment amount ({payment_amount}) exceeds invoice outstanding balance ({current_outstanding})"
        )
    if bank_account and bank_account.company_id != invoice.company_id:
        return False, None, "Selected bank account does not belong to this invoice company."

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
                bank_account=bank_account,
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
            new_outstanding = max(Decimal('0'), current_outstanding - payment_amount)
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
