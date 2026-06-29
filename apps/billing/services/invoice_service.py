from decimal import Decimal, ROUND_CEILING
import uuid
from datetime import date
import random
import string

import nepali_datetime
from django.db.models import Max


from apps.company.models import Company, FiscalYear
from apps.utils.constant import *

def calculate_subtotal(invoice):
    """Calculate subtotal as sum of item totals after item-level discounts."""
    if invoice.pk:
        subtotal = sum(item.total_price for item in invoice.items.all())
        return Decimal(subtotal).quantize(Decimal('0.01'))
    return Decimal('0')

def calculate_item_discounts(invoice):
    """Calculate total item-level discount amount across all items."""
    if invoice.pk:
        total_item_discount = Decimal('0')
        for item in invoice.items.all():
            base = Decimal(item.quantity) * item.price
            if item.discount_amount > 0:
                total_item_discount += item.discount_amount
            elif item.discount_percent > 0:
                total_item_discount += (base * item.discount_percent / Decimal('100')).quantize(Decimal('0.01'))
        return total_item_discount
    return Decimal('0')

def calculate_discount_amount(subtotal, discount_percent):
    if discount_percent > 0:
        return (subtotal * discount_percent / Decimal('100')).quantize(Decimal('0.01'))
    return Decimal('0')

def calculate_tax_amount(subtotal, discount_amount, tax_percent):
    taxable_amount = subtotal - discount_amount
    return (taxable_amount * tax_percent / Decimal('100')).quantize(Decimal('0.01'))

def calculate_total(invoice):
    # Subtotal is the sum of item totals (after item-level discounts)
    invoice.subtotal = calculate_subtotal(invoice)
    
    # Calculate total item-level discounts
    item_discount_total = calculate_item_discounts(invoice)
    
    # Calculate global discount on top of item discounts
    global_discount = calculate_discount_amount(invoice.subtotal, invoice.discount_percent)
    
    # Total discount = item discounts + global discount
    invoice.discount_amount = item_discount_total + global_discount
    
    invoice.tax_amount = calculate_tax_amount(invoice.subtotal, global_discount, invoice.tax_percent)
    invoice.total = (invoice.subtotal - global_discount + invoice.tax_amount).quantize(Decimal('0.01'))
    return invoice.total


def generate_invoice_number(company_id, doc_type: str = "INV") -> str:
    """
    Format: {COMPANY}-{TYPE}-{FY}-{NNNN}
    e.g.   DPS-INV-2082/83-0001
    """
    today_np = nepali_datetime.date.today()
    try:
        company = Company.active_objects.get(id=company_id)
        company_prefix = company.name[:3].upper().strip().ljust(3, 'X')
        fiscal_year = FiscalYear.active_objects.filter(is_active=True, company=company).first()
        fiscal_year_name = fiscal_year.name if fiscal_year else today_np.strftime("%y/%m/%d")
    except (Company.DoesNotExist, AttributeError):
        company_prefix = "INV"
        fiscal_year_name = today_np.strftime("%y/%m/%d")

    prefix = f"{company_prefix}-{doc_type}-{fiscal_year_name}-"

    from apps.billing.models import Invoice
    # Use company-wide max to respect the unique_invoice_seq_per_company constraint
    last_seq = Invoice.objects.filter(
        company_id=company_id,
    ).aggregate(max_seq=Max('sequence_number'))

    sequence = (last_seq['max_seq'] or 0) + 1

    invoice_number = f"{prefix}{sequence:04d}"
    while Invoice.objects.filter(
        company_id=company_id, sequence_number=sequence
    ).exists() or Invoice.objects.filter(invoice_number=invoice_number).exists():
        sequence += 1
        invoice_number = f"{prefix}{sequence:04d}"

    return invoice_number, sequence

def can_approve(status: str) -> bool:
    return status in [StatusChoicesEnum.Draft, StatusChoicesEnum.Submitted]

def can_pay(status: str) -> bool:
    return status in [StatusChoicesEnum.Approved, StatusChoicesEnum.Sent]

def can_cancel(status: str) -> bool:
    return status not in [StatusChoicesEnum.Cancelled, StatusChoicesEnum.Paid]