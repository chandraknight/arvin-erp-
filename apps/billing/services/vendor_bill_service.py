from decimal import Decimal

def update_vendor_bill_total(vendor_bill):
    vendor_bill.total_amount = sum(
        item.quantity * item.price for item in vendor_bill.items.all()
    ).quantize(Decimal('0.00'))
    vendor_bill.save(update_fields=['total_amount'])