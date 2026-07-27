"""
NFRS 1 — Prepaid expense recognition & amortization.

create_prepaid_expense(...)  → posts the initial recognition entry and creates the PrepaidExpense row.
post_prepaid_amortization(prepaid, period_start, period_end, posted_by) → posts one period's amortization.

Mirrors apps/bookkeeping/fixed_asset_service.py's asset + periodic-log + idempotency-per-period pattern.
"""
from decimal import Decimal

from django.db import transaction

from .models import (
    PrepaidExpense, PrepaidExpenseAmortizationLog, post_journal_entry, get_or_create_system_account,
)

_PREPAID_ASSET_DEFAULT_NAME = 'Prepaid Expenses'
_AMORTIZATION_EXPENSE_DEFAULT_NAME = 'Prepaid Expense Amortization'


@transaction.atomic
def create_prepaid_expense(company, name, total_amount, start_date, end_date, paid_from_account,
                            description='', created_by=None):
    """Posts DR Prepaid Expenses (asset) / CR paid_from_account, then creates the PrepaidExpense row."""
    if total_amount <= Decimal('0.00'):
        raise ValueError("Prepaid expense total amount must be greater than zero.")
    if end_date <= start_date:
        raise ValueError("End date must be after the start date.")

    prepaid_asset_acc = get_or_create_system_account(
        company, _PREPAID_ASSET_DEFAULT_NAME, 'ASSET', code='1220', is_current=True
    )
    amortization_expense_acc = get_or_create_system_account(
        company, _AMORTIZATION_EXPENSE_DEFAULT_NAME, 'EXPENSE', code='5940'
    )

    post_journal_entry(
        company=company,
        date=start_date,
        description=f"Prepaid expense recognized — {name}",
        lines=[
            {'account': prepaid_asset_acc, 'entry_type': 'DEBIT', 'amount': total_amount, 'narration': name},
            {'account': paid_from_account, 'entry_type': 'CREDIT', 'amount': total_amount, 'narration': name},
        ],
        created_by=created_by,
        source_type='PREPAID_AMORTIZATION',
    )

    return PrepaidExpense.objects.create(
        company=company,
        name=name,
        description=description,
        total_amount=total_amount,
        start_date=start_date,
        end_date=end_date,
        prepaid_asset_account=prepaid_asset_acc,
        amortization_expense_account=amortization_expense_acc,
        paid_from_account=paid_from_account,
        created_by=created_by,
    )


@transaction.atomic
def post_prepaid_amortization(prepaid, period_start, period_end, posted_by=None):
    """
    Post one period's amortization: DR Amortization Expense / CR Prepaid Expenses (asset).

    Idempotent per period (mirrors fixed_asset_service.post_depreciation) and capped
    at the remaining unamortized balance.
    """
    if prepaid.status != 'ACTIVE':
        raise ValueError(f"Prepaid expense '{prepaid.name}' is {prepaid.status} — cannot post amortization.")

    existing = PrepaidExpenseAmortizationLog.objects.filter(
        prepaid_expense=prepaid, period_start=period_start, period_end=period_end,
    ).first()
    if existing:
        raise ValueError(
            f"Amortization already posted for '{prepaid.name}' period {period_start}–{period_end}."
        )

    total_days = (prepaid.end_date - prepaid.start_date).days + 1
    period_days = (period_end - period_start).days + 1
    if total_days <= 0:
        raise ValueError(f"Prepaid expense '{prepaid.name}' has an invalid date range.")

    amount = (prepaid.total_amount * Decimal(period_days) / Decimal(total_days)).quantize(Decimal('0.01'))
    remaining = prepaid.remaining_amount
    if remaining <= Decimal('0.00'):
        raise ValueError(f"Prepaid expense '{prepaid.name}' is fully amortized.")
    amount = min(amount, remaining)

    if amount <= Decimal('0.00'):
        raise ValueError(f"Amortization amount is zero for '{prepaid.name}'.")

    entry = post_journal_entry(
        company=prepaid.company,
        date=period_end,
        description=f"Prepaid expense amortization — {prepaid.name} ({period_start} to {period_end})",
        lines=[
            {'account': prepaid.amortization_expense_account, 'entry_type': 'DEBIT', 'amount': amount,
             'narration': f'Amortization of {prepaid.name}'},
            {'account': prepaid.prepaid_asset_account, 'entry_type': 'CREDIT', 'amount': amount,
             'narration': f'Prepaid expense reduction — {prepaid.name}'},
        ],
        created_by=posted_by,
        source_type='PREPAID_AMORTIZATION',
    )

    prepaid.accumulated_amortization += amount
    if prepaid.remaining_amount <= Decimal('0.00'):
        prepaid.status = 'FULLY_AMORTIZED'
    prepaid.save(update_fields=['accumulated_amortization', 'status', 'updated_at'])

    return PrepaidExpenseAmortizationLog.objects.create(
        prepaid_expense=prepaid,
        journal_entry=entry,
        period_start=period_start,
        period_end=period_end,
        amount=amount,
    )
