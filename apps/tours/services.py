from decimal import Decimal
from django.utils import timezone
from apps.billing.models import Invoice, InvoiceItem
from apps.billing.services.invoice_service import generate_invoice_number


def issue_invoice_from_booking(booking, user):
    """Create a billing.Invoice from a confirmed TourBooking."""
    if booking.has_invoice:
        return booking.invoice

    invoice_number, seq, fy = generate_invoice_number(booking.company.id)

    invoice = Invoice.objects.create(
        company=booking.company,
        customer=booking.customer,
        transaction_date=timezone.now().date(),
        subtotal=booking.subtotal,
        discount_amount=booking.discount_amount,
        tax_amount=booking.tax_amount,
        tax_percent=booking.tax_percent,
        total=booking.total,
        outstanding_balance=booking.total,
        invoice_number=invoice_number,
        sequence_number=seq,
        fiscal_year=fy,
        created_by=user,
    )

    for item in booking.items.filter(is_deleted=False):
        InvoiceItem.objects.create(
            invoice=invoice,
            description=item.description,
            quantity=int(item.quantity),
            price=item.unit_price,
            discount_percent=item.discount_percent,
        )

    booking.invoice = invoice
    booking.status = 'CONFIRMED'
    booking.save(update_fields=['invoice', 'status'])

    return invoice
