from decimal import Decimal

def update_vendor_bill_total(vendor_bill):
    """
    Recompute subtotal, tax_amount and total_amount from items and the bill's
    tax_percent.  Saves all three fields in one update so the post_save signal
    fires exactly once with the correct, final figures.
    """
    subtotal = sum(
        item.quantity * item.price for item in vendor_bill.items.all()
    ) or Decimal('0.00')
    subtotal = Decimal(str(subtotal)).quantize(Decimal('0.01'))
    tax_rate = Decimal(str(vendor_bill.tax_percent or 0))
    tax_amount = (subtotal * tax_rate / Decimal('100')).quantize(Decimal('0.01'))
    vendor_bill.tax_amount = tax_amount
    vendor_bill.total_amount = (subtotal + tax_amount).quantize(Decimal('0.01'))
    vendor_bill.save(update_fields=['tax_percent', 'tax_amount', 'total_amount'])