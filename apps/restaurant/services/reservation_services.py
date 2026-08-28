import logging
from django.db import transaction

from apps.restaurant.models import RestaurantTable, TableReservation

logger = logging.getLogger(__name__)
audit = logging.getLogger('audit')


@transaction.atomic
def reserve_table(
    company, table: RestaurantTable, guest_name: str, reserved_for,
    guest_phone: str = '', party_size: int = 1, notes: str = '', created_by=None
) -> TableReservation:
    if table.status != 'AVAILABLE':
        raise ValueError(f"Table {table.label} is not available for reservation.")

    reservation = TableReservation.objects.create(
        company=company,
        table=table,
        guest_name=guest_name,
        guest_phone=guest_phone,
        party_size=party_size,
        reserved_for=reserved_for,
        notes=notes,
        status='PENDING',
        created_by=created_by,
    )
    table.status = 'RESERVED'
    table.save(update_fields=['status'])

    audit.info(
        'TABLE_RESERVED table=%s guest=%s reserved_for=%s', table.table_number, guest_name, reserved_for,
    )
    return reservation


def seat_reservation(reservation: TableReservation, request, covers: int = None, waiter_name: str = ''):
    """Convert a pending reservation into an open dining order. Table stays OCCUPIED."""
    from apps.restaurant.services.order_services import open_order

    if reservation.status != 'PENDING':
        raise ValueError(f"Reservation is {reservation.status} — only PENDING reservations can be seated.")

    with transaction.atomic():
        order = open_order(
            request=request,
            table=reservation.table,
            covers=covers or reservation.party_size,
            waiter_name=waiter_name,
        )
        reservation.status = 'SEATED'
        reservation.updated_by = request.user
        reservation.save(update_fields=['status', 'updated_by'])

        audit.info(
            'RESERVATION_SEATED table=%s guest=%s order=%s actor=%s',
            reservation.table.table_number, reservation.guest_name, order.order_number, request.user.email,
        )
    return order


def cancel_reservation(reservation: TableReservation, request) -> TableReservation:
    if reservation.status != 'PENDING':
        raise ValueError(f"Reservation is {reservation.status} — only PENDING reservations can be cancelled.")

    with transaction.atomic():
        reservation.status = 'CANCELLED'
        reservation.updated_by = request.user
        reservation.save(update_fields=['status', 'updated_by'])

        reservation.table.status = 'AVAILABLE'
        reservation.table.save(update_fields=['status'])

        audit.info(
            'RESERVATION_CANCELLED table=%s guest=%s actor=%s',
            reservation.table.table_number, reservation.guest_name, request.user.email,
        )
    return reservation
