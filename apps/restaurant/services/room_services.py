import logging
from decimal import Decimal
from django.db import transaction
from django.utils import timezone

from apps.restaurant.models import Room, RoomBooking, RoomCharge

logger = logging.getLogger(__name__)
audit = logging.getLogger('audit')


@transaction.atomic
def create_booking(
    company, room: Room, guest_name: str, guest_phone: str,
    check_in, check_out, adult_count: int = 1, child_count: int = 0,
    guest_email: str = '', notes: str = '', created_by=None
) -> RoomBooking:
    if room.status not in ('AVAILABLE', 'RESERVED'):
        raise ValueError(f"Room {room.room_number} is not available for booking.")
    if check_out <= check_in:
        raise ValueError("Check-out date must be after check-in date.")

    # Detect overlap with existing active bookings
    overlap = RoomBooking.objects.filter(
        room=room,
        status__in=['CONFIRMED', 'CHECKED_IN'],
        check_in__lt=check_out,
        check_out__gt=check_in,
    ).exists()
    if overlap:
        raise ValueError(f"Room {room.room_number} is already booked for part of that period.")

    booking = RoomBooking.objects.create(
        company=company,
        room=room,
        guest_name=guest_name,
        guest_phone=guest_phone,
        guest_email=guest_email,
        check_in=check_in,
        check_out=check_out,
        adult_count=adult_count,
        child_count=child_count,
        rate_per_night=room.room_type.rate_per_night,
        notes=notes,
        status='CONFIRMED',
        created_by=created_by,
    )
    room.status = 'RESERVED'
    room.save(update_fields=['status'])

    audit.info('ROOM_BOOKED room=%s guest=%s check_in=%s', room.room_number, guest_name, check_in)
    return booking


@transaction.atomic
def check_in_room(booking: RoomBooking, user=None) -> RoomBooking:
    if booking.status != 'CONFIRMED':
        raise ValueError(f"Booking is {booking.status} — only CONFIRMED bookings can be checked in.")

    booking.status = 'CHECKED_IN'
    booking.checked_in_at = timezone.now()
    booking.updated_by = user
    booking.save(update_fields=['status', 'checked_in_at', 'updated_by'])

    booking.room.status = 'OCCUPIED'
    booking.room.save(update_fields=['status'])

    audit.info('ROOM_CHECKED_IN room=%s guest=%s', booking.room.room_number, booking.guest_name)
    return booking


@transaction.atomic
def check_out_room(booking: RoomBooking, user=None) -> 'billing.Invoice':
    from apps.billing.models import Invoice, InvoiceItem
    from apps.billing.services.invoice_service import generate_invoice_number
    from apps.company.services.company_services import setup_default_ledger_accounts

    if booking.status != 'CHECKED_IN':
        raise ValueError(f"Booking is {booking.status} — only CHECKED_IN bookings can be checked out.")

    company = booking.company
    setup_default_ledger_accounts(company)

    invoice_number, seq, fy = generate_invoice_number(company.id)

    # Room accommodation line
    subtotal = booking.room_charge_total
    extra = booking.extra_charge_total
    grand = booking.grand_total
    tax_rate = company.tax_rate
    tax_amount = (grand * tax_rate / Decimal('100')).quantize(Decimal('0.01'))
    total = grand + tax_amount

    invoice = Invoice.objects.create(
        company=company,
        customer=None,
        invoice_number=invoice_number,
        sequence_number=seq,
        fiscal_year=fy,
        transaction_date=timezone.now().date(),
        subtotal=grand,
        discount_amount=Decimal('0.00'),
        tax_amount=tax_amount,
        total=total,
        outstanding_balance=total,
        tax_percent=tax_rate,
        status='ISSUED',
        created_by=user,
    )

    InvoiceItem.objects.create(
        invoice=invoice,
        description=f"Room {booking.room.room_number} — {booking.nights} night(s) × Rs {booking.rate_per_night}",
        quantity=booking.nights,
        price=booking.rate_per_night,
    )
    for charge in booking.charges.all():
        InvoiceItem.objects.create(
            invoice=invoice,
            description=charge.description,
            quantity=1,
            price=charge.amount,
        )

    booking.status = 'CHECKED_OUT'
    booking.checked_out_at = timezone.now()
    booking.invoice = invoice
    booking.updated_by = user
    booking.save(update_fields=['status', 'checked_out_at', 'invoice', 'updated_by'])

    booking.room.status = 'CHECKOUT'
    booking.room.save(update_fields=['status'])

    audit.info('ROOM_CHECKED_OUT room=%s guest=%s invoice=%s', booking.room.room_number, booking.guest_name, invoice_number)
    return invoice


def add_room_charge(booking: RoomBooking, description: str, amount: Decimal, user=None) -> RoomCharge:
    if booking.status not in ('CONFIRMED', 'CHECKED_IN'):
        raise ValueError("Charges can only be added to active bookings.")
    charge = RoomCharge.objects.create(
        booking=booking,
        description=description,
        amount=amount,
        created_by=user,
    )
    audit.info('ROOM_CHARGE_ADDED booking=%s desc=%s amount=%s', booking.pk, description, amount)
    return charge


def cancel_booking(booking: RoomBooking, reason: str = '', user=None) -> RoomBooking:
    if booking.status in ('CHECKED_IN', 'CHECKED_OUT'):
        raise ValueError(f"Cannot cancel a booking that is {booking.status}.")
    if booking.status == 'CANCELLED':
        raise ValueError("Booking is already cancelled.")
    with transaction.atomic():
        booking.status = 'CANCELLED'
        booking.notes = (booking.notes or '') + f'\nCANCELLED: {reason}'
        booking.updated_by = user
        booking.save(update_fields=['status', 'notes', 'updated_by'])
        if booking.room.status == 'RESERVED':
            booking.room.status = 'AVAILABLE'
            booking.room.save(update_fields=['status'])
    audit.info('ROOM_BOOKING_CANCELLED booking=%s reason=%s', booking.pk, reason)
    return booking
