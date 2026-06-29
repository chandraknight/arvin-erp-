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

def apply_credit_note(invoice, credit_note):
    invoice.outstanding_balance = (invoice.outstanding_balance - credit_note.amount).quantize(Decimal('0.00'))
    invoice.save(update_fields=['outstanding_balance'])
    credit_note.status = StatusChoicesEnum.Applied
    credit_note.save(update_fields=['status'])

def apply_debit_note(invoice, debit_note):
    invoice.outstanding_balance = (invoice.outstanding_balance + debit_note.amount).quantize(Decimal('0.00'))
    invoice.save(update_fields=['outstanding_balance'])
    debit_note.status = StatusChoicesEnum.Applied
    debit_note.save(update_fields=['status'])
