from decimal import Decimal
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

import nepali_datetime

from apps.billing.models import Invoice, InvoiceItem
from apps.billing.services.invoice_service import generate_invoice_number
from apps.company.models import Company, FiscalYear


def _generate_tours_number(company_id, doc_type, model, field_name):
    """
    Format: {COMPANY_PREFIX}-{TYPE}-{FISCAL_YEAR}-{NNNN}, e.g. DPS-ENQ-2082/83-0001.
    Same fiscal-year-scoped, race-safe pattern as generate_invoice_number.
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

    fy_filter = {'fiscal_year': fiscal_year} if fiscal_year else {'fiscal_year__isnull': True}
    with transaction.atomic():
        last_seq = model.objects.select_for_update().filter(
            company_id=company_id,
            **fy_filter,
        ).aggregate(max_seq=Max('sequence_number'))

        sequence = (last_seq['max_seq'] or 0) + 1

        number = f"{prefix}{sequence:04d}"
        while model.objects.filter(
            company_id=company_id, fiscal_year=fiscal_year, sequence_number=sequence
        ).exists() or model.objects.filter(**{field_name: number}).exists():
            sequence += 1
            number = f"{prefix}{sequence:04d}"

    return number, sequence, fiscal_year


def generate_enquiry_number(company_id):
    from apps.tours.models import TourEnquiry
    return _generate_tours_number(company_id, 'ENQ', TourEnquiry, 'enquiry_number')


def generate_booking_number(company_id):
    from apps.tours.models import TourBooking
    return _generate_tours_number(company_id, 'BKG', TourBooking, 'booking_number')


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
