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

def apply_credit_note(credit_note):
    """Sales return: reduce the customer invoice balance; journal posts via signal."""
    invoice = credit_note.invoice
    if invoice:
        invoice.outstanding_balance = max(
            Decimal('0.00'),
            (invoice.outstanding_balance - credit_note.amount).quantize(Decimal('0.01')),
        )
        invoice.save(update_fields=['outstanding_balance'])
    credit_note.status = StatusChoicesEnum.Applied.value
    credit_note.save(update_fields=['status'])


def apply_debit_note(debit_note):
    """Purchase return: DR Accounts Payable journal posts via signal."""
    debit_note.status = StatusChoicesEnum.Applied.value
    debit_note.save(update_fields=['status'])
