"""
Nepal TDS (withholding tax) calculation for vendor bills.

calculate_tds(vendor_bill) → Decimal TDS amount, quantized to 0.01.
"""
from decimal import Decimal


def calculate_tds(vendor_bill):
    from apps.bookkeeping.models import TDSRate

    if not vendor_bill.tds_category:
        return Decimal('0.00')

    company = (
        vendor_bill.purchase_order.company
        if vendor_bill.purchase_order
        else vendor_bill.vendor.company
    )

    tds_rate = TDSRate.objects.filter(
        company=company,
        category=vendor_bill.tds_category,
        is_active=True,
        effective_from__lte=vendor_bill.bill_date,
    ).order_by('-effective_from').first()

    if not tds_rate:
        return Decimal('0.00')

    amount = (vendor_bill.total_amount * tds_rate.rate / Decimal('100'))
    return amount.quantize(Decimal('0.01'))
