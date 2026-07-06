from datetime import date
import uuid
from decimal import Decimal
from apps.utils.constant import *

def generate_credit_note_number():
    today = date.today().strftime("%Y%m%d")
    unique_part = uuid.uuid4().hex[:4].upper()
    return f"CN-{today}-{unique_part}"

def generate_debit_note_number():
    today = date.today().strftime("%Y%m%d")
    unique_part = uuid.uuid4().hex[:4].upper()
    return f"DN-{today}-{unique_part}"


def _shift_invoice_balance(invoice, delta):
    """Adjust an invoice's outstanding balance via queryset update —
    instance.save() would re-fire the invoice journal signal."""
    if not invoice or not delta:
        return
    from apps.billing.models import Invoice
    new_balance = (invoice.outstanding_balance + delta).quantize(Decimal('0.00'))
    Invoice.objects.filter(pk=invoice.pk).update(outstanding_balance=new_balance)
    invoice.outstanding_balance = new_balance


def apply_credit_note(credit_note, old_invoice=None, old_amount=Decimal('0.00')):
    """Apply a sales-return credit note: reduce the customer invoice balance
    and mark the note APPLIED, which posts the NFRS journal entry via the
    post_save signal. On re-apply, pass the previously applied invoice/amount
    so the earlier balance effect is reverted first."""
    _shift_invoice_balance(old_invoice, +old_amount)
    _shift_invoice_balance(credit_note.invoice, -credit_note.amount)
    credit_note.status = StatusChoicesEnum.Applied.value
    credit_note.save(update_fields=['status'])


def apply_debit_note(debit_note, old_invoice=None, old_amount=Decimal('0.00')):
    """Apply a debit note. Purchase returns (vendor/vendor_bill set) only post
    the journal entry; customer-side notes also increase the invoice balance."""
    _shift_invoice_balance(old_invoice, -old_amount)
    is_purchase_return = bool(debit_note.vendor_id or debit_note.vendor_bill_id)
    if not is_purchase_return:
        _shift_invoice_balance(debit_note.invoice, +debit_note.amount)
    debit_note.status = StatusChoicesEnum.Applied.value
    debit_note.save(update_fields=['status'])
