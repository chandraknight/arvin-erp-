from datetime import date
from decimal import Decimal

import nepali_datetime
from django.db import transaction
from django.db.models import Max

from apps.company.models import Company, FiscalYear
from apps.utils.constant import *


def _generate_note_number(company_id, doc_type, model, field_name):
    """
    Shared sequential, fiscal-year-scoped number generator for Credit/Debit
    Notes. Mirrors apps.billing.services.invoice_service.generate_invoice_number
    so numbering resets per fiscal year and continues from that fiscal year's
    last number when you switch back to it, instead of a random suffix.
    Returns (number, sequence, fiscal_year).
    """
    today_np = nepali_datetime.date.today()
    fiscal_year = None
    try:
        company = Company.active_objects.get(id=company_id)
        company_prefix = company.name[:3].upper().strip().ljust(3, 'X')
        fiscal_year = FiscalYear.active_objects.filter(is_active=True, company=company).first()
        fiscal_year_name = fiscal_year.name if fiscal_year else today_np.strftime("%y/%m/%d")
    except (Company.DoesNotExist, AttributeError):
        company_prefix = doc_type
        fiscal_year_name = today_np.strftime("%y/%m/%d")

    prefix = f"{company_prefix}-{doc_type}-{fiscal_year_name}-"

    with transaction.atomic():
        fy_filter = {'fiscal_year': fiscal_year} if fiscal_year else {'fiscal_year__isnull': True}
        last_seq = model.objects.select_for_update().filter(
            company_id=company_id, **fy_filter,
        ).aggregate(max_seq=Max('sequence_number'))['max_seq'] or 0

        sequence = last_seq + 1
        number = f"{prefix}{sequence:04d}"
        while model.objects.filter(**{field_name: number}).exists():
            sequence += 1
            number = f"{prefix}{sequence:04d}"

    return number, sequence, fiscal_year


def generate_credit_note_number(company_id):
    from apps.billing.models import CreditNote
    return _generate_note_number(company_id, 'CN', CreditNote, 'credit_note_number')


def generate_debit_note_number(company_id):
    from apps.billing.models import DebitNote
    return _generate_note_number(company_id, 'DN', DebitNote, 'debit_note_number')

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
