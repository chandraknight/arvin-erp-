"""
apps/pos/services/shift_services.py
====================================
Till shift / cash drawer reconciliation — opening float, cash in/out log,
and end-of-day expected-vs-counted cash variance.
"""

import logging
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.pos.models import PosCashMovement, POSSale, PosShift

logger = logging.getLogger(__name__)
audit = logging.getLogger('audit')


def get_active_shift(company, branch=None, terminal_name=''):
    return PosShift.active_objects.filter(
        company=company, branch=branch, terminal_name=terminal_name, status='OPEN'
    ).first()


@transaction.atomic
def open_shift(company, branch, user, opening_float, terminal_name=''):
    if get_active_shift(company, branch, terminal_name):
        raise ValueError("A shift is already open for this terminal.")

    shift = PosShift.objects.create(
        company=company,
        branch=branch,
        terminal_name=terminal_name,
        opened_by=user,
        opening_float=opening_float,
        created_by=user,
    )

    audit.info(
        'SHIFT_OPENED shift=%s company=%s opening_float=%s actor=%s',
        shift.pk, company, opening_float, user.email,
    )
    return shift


@transaction.atomic
def record_cash_movement(shift, movement_type, amount, reason, user):
    if shift.status != 'OPEN':
        raise ValueError("Cannot record a cash movement on a closed shift.")
    if amount <= 0:
        raise ValueError("Amount must be greater than zero.")

    movement = PosCashMovement.objects.create(
        shift=shift,
        movement_type=movement_type,
        amount=amount,
        reason=reason,
        recorded_by=user,
        created_by=user,
    )

    audit.info(
        'SHIFT_CASH_MOVEMENT shift=%s type=%s amount=%s actor=%s',
        shift.pk, movement_type, amount, user.email,
    )
    return movement


def _compute_expected_cash(shift):
    cash_sales = POSSale.active_objects.filter(
        shift=shift, payment_method='CASH'
    ).aggregate(total=Sum('total'))['total'] or Decimal('0.00')

    cash_in = shift.cash_movements.filter(movement_type='CASH_IN').aggregate(
        total=Sum('amount'))['total'] or Decimal('0.00')
    cash_out = shift.cash_movements.filter(movement_type='CASH_OUT').aggregate(
        total=Sum('amount'))['total'] or Decimal('0.00')

    return shift.opening_float + cash_sales + cash_in - cash_out


@transaction.atomic
def close_shift(shift, counted_cash, notes, user):
    if shift.status != 'OPEN':
        raise ValueError("Shift is already closed.")

    expected_cash = _compute_expected_cash(shift)
    variance = counted_cash - expected_cash

    shift.expected_cash = expected_cash
    shift.counted_cash = counted_cash
    shift.variance = variance
    shift.closing_notes = notes
    shift.status = 'CLOSED'
    shift.closed_by = user
    shift.closed_at = timezone.now()
    shift.updated_by = user
    shift.save(update_fields=[
        'expected_cash', 'counted_cash', 'variance', 'closing_notes',
        'status', 'closed_by', 'closed_at', 'updated_by',
    ])

    audit.info(
        'SHIFT_CLOSED shift=%s expected=%s counted=%s variance=%s actor=%s',
        shift.pk, expected_cash, counted_cash, variance, user.email,
    )
    return shift
