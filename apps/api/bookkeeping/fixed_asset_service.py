"""
NFRS 13 (IAS 16) — Fixed Asset depreciation service.

post_depreciation(asset, period_start, period_end, posted_by)
  → creates the double-entry journal and updates accumulated_depreciation.

Idempotent: raises ValueError if a log already exists for the same period.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from datetime import date

from django.db import transaction

logger = logging.getLogger(__name__)

_ACCUM_DEP_DEFAULT_NAME = 'Accumulated Depreciation'
_DEP_EXPENSE_DEFAULT_NAME = 'Depreciation Expense'


def _get_or_create_account(company, name, account_type, code=None):
    from .models import LedgerAccount
    acc, _ = LedgerAccount.objects.get_or_create(
        company=company,
        name=name,
        defaults={
            'account_type': account_type,
            'code': code,
            'system_created': True,
            'is_current': account_type not in ('ASSET',),
        },
    )
    return acc


@transaction.atomic
def post_depreciation(asset, period_start: date, period_end: date, posted_by=None):
    """
    Post a depreciation journal for *asset* covering [period_start, period_end].

    Journal entry (NFRS 13 cost model):
      DR  Depreciation Expense          amount
      CR  Accumulated Depreciation      amount

    Returns the created FixedAssetDepreciationLog.
    Raises ValueError if:
      - asset is disposed/impaired
      - a depreciation log already exists for this period
      - depreciation amount is zero or negative
    """
    from .models import FixedAsset, FixedAssetDepreciationLog, JournalEntry, JournalEntryLine

    if asset.status != 'ACTIVE':
        raise ValueError(f"Asset '{asset.name}' is {asset.status} — cannot post depreciation.")

    existing = FixedAssetDepreciationLog.objects.filter(
        asset=asset,
        period_start=period_start,
        period_end=period_end,
    ).first()
    if existing:
        raise ValueError(
            f"Depreciation already posted for asset '{asset.name}' "
            f"period {period_start}–{period_end}."
        )

    # Pro-rate SLM by days in period vs 365
    if asset.depreciation_method == 'SLM':
        annual = asset.annual_depreciation()
        days = (period_end - period_start).days + 1
        amount = (annual * Decimal(days) / Decimal('365')).quantize(Decimal('0.01'))
    else:
        # WDV: use annual rate, pro-rate by days
        annual = asset.annual_depreciation()
        days = (period_end - period_start).days + 1
        amount = (annual * Decimal(days) / Decimal('365')).quantize(Decimal('0.01'))

    # Don't depreciate below residual value
    remaining = asset.net_book_value - asset.residual_value
    if remaining <= Decimal('0.00'):
        raise ValueError(f"Asset '{asset.name}' is fully depreciated (NBV ≤ residual value).")
    amount = min(amount, remaining)

    if amount <= Decimal('0.00'):
        raise ValueError(f"Depreciation amount is zero for asset '{asset.name}'.")

    company = asset.company

    # Resolve ledger accounts
    dep_expense_acc = asset.depreciation_expense_account or _get_or_create_account(
        company, _DEP_EXPENSE_DEFAULT_NAME, 'EXPENSE', code='5200'
    )
    accum_dep_acc = asset.accumulated_dep_account or _get_or_create_account(
        company, _ACCUM_DEP_DEFAULT_NAME, 'ASSET', code='1510'
    )
    # Accumulated depreciation is a contra-asset — we keep it as ASSET type
    # with credit-normal balance so NBV = cost - accum_dep

    entry = JournalEntry.objects.create(
        company=company,
        date=period_end,
        description=f'Depreciation — {asset.name} ({period_start} to {period_end})',
        created_by=posted_by,
        journal_type='DEPRECIATION',
    )
    JournalEntryLine.objects.create(
        journal_entry=entry,
        account=dep_expense_acc,
        entry_type='DEBIT',
        amount=amount,
        narration=f'Depreciation {asset.depreciation_method}',
    )
    JournalEntryLine.objects.create(
        journal_entry=entry,
        account=accum_dep_acc,
        entry_type='CREDIT',
        amount=amount,
        narration=f'Accumulated depreciation {asset.name}',
    )
    from .models import assert_balanced
    assert_balanced(entry)

    asset.accumulated_depreciation += amount
    asset.save(update_fields=['accumulated_depreciation', 'updated_at'])

    log = FixedAssetDepreciationLog.objects.create(
        asset=asset,
        journal_entry=entry,
        period_start=period_start,
        period_end=period_end,
        amount=amount,
        created_by=posted_by,
    )

    logger.info(
        'depreciation_posted asset=%s period=%s-%s amount=%s journal=%s',
        asset.id, period_start, period_end, amount, entry.id,
    )
    return log


@transaction.atomic
def post_disposal(asset, disposal_date: date, sale_proceeds: Decimal = Decimal('0.00'), posted_by=None):
    """
    Derecognize *asset* on disposal (NFRS 13 / IAS 16 para 67-72).

    Journal entry:
      DR  Accumulated Depreciation     accumulated_depreciation
      DR  Cash/Bank (or Disposal AR)   sale_proceeds        [only if proceeds > 0]
      DR  Loss on Disposal             loss                 [only if NBV > proceeds]
      CR  Fixed Asset (cost)           asset.cost
      CR  Gain on Disposal             gain                 [only if proceeds > NBV]

    Sets asset.status = 'DISPOSED' and asset.disposal_date.
    Raises ValueError if asset is already disposed.
    """
    from .models import JournalEntry, JournalEntryLine, assert_balanced

    if asset.status == 'DISPOSED':
        raise ValueError(f"Asset '{asset.name}' is already disposed.")

    company = asset.company
    asset_acc = asset.asset_account or _get_or_create_account(
        company, 'Fixed Assets', 'ASSET', code='1500'
    )
    accum_dep_acc = asset.accumulated_dep_account or _get_or_create_account(
        company, _ACCUM_DEP_DEFAULT_NAME, 'ASSET', code='1510'
    )
    cash_acc = _get_or_create_account(company, 'Cash', 'ASSET', code='1000')

    net_book_value = asset.net_book_value
    gain = max(sale_proceeds - net_book_value, Decimal('0.00'))
    loss = max(net_book_value - sale_proceeds, Decimal('0.00'))

    entry = JournalEntry.objects.create(
        company=company,
        date=disposal_date,
        description=f'Disposal — {asset.name}',
        created_by=posted_by,
        journal_type='DISPOSAL',
    )
    lines = [JournalEntryLine(
        journal_entry=entry, account=accum_dep_acc, entry_type='DEBIT',
        amount=asset.accumulated_depreciation, narration='Derecognize accumulated depreciation',
    )]
    if sale_proceeds > Decimal('0.00'):
        lines.append(JournalEntryLine(
            journal_entry=entry, account=cash_acc, entry_type='DEBIT',
            amount=sale_proceeds, narration='Sale proceeds on disposal',
        ))
    if loss > Decimal('0.00'):
        loss_acc = _get_or_create_account(company, 'Loss on Disposal of Asset', 'EXPENSE', code='5900')
        lines.append(JournalEntryLine(
            journal_entry=entry, account=loss_acc, entry_type='DEBIT',
            amount=loss, narration=f'Loss on disposal of {asset.name}',
        ))
    lines.append(JournalEntryLine(
        journal_entry=entry, account=asset_acc, entry_type='CREDIT',
        amount=asset.cost, narration='Derecognize asset cost',
    ))
    if gain > Decimal('0.00'):
        gain_acc = _get_or_create_account(company, 'Gain on Disposal of Asset', 'REVENUE', code='4900')
        lines.append(JournalEntryLine(
            journal_entry=entry, account=gain_acc, entry_type='CREDIT',
            amount=gain, narration=f'Gain on disposal of {asset.name}',
        ))
    JournalEntryLine.objects.bulk_create(lines)
    assert_balanced(entry)

    asset.status = 'DISPOSED'
    asset.disposal_date = disposal_date
    asset.save(update_fields=['status', 'disposal_date', 'updated_at'])

    logger.info(
        'disposal_posted asset=%s date=%s proceeds=%s gain=%s loss=%s journal=%s',
        asset.id, disposal_date, sale_proceeds, gain, loss, entry.id,
    )
    return entry


def depreciation_schedule(asset) -> list[dict]:
    """
    Return the full depreciation schedule for *asset* from acquisition to full depreciation.
    Each row: { year, opening_nbv, depreciation, closing_nbv, accumulated }
    """
    rows = []
    nbv = asset.cost
    accum = Decimal('0.00')
    depreciable = asset.cost - asset.residual_value

    for year in range(1, asset.useful_life_years + 1):
        if asset.depreciation_method == 'SLM':
            dep = (depreciable / asset.useful_life_years).quantize(Decimal('0.01'))
        else:
            rate = asset.depreciation_rate or Decimal('0.00')
            dep = (nbv * rate / Decimal('100')).quantize(Decimal('0.01'))

        dep = min(dep, nbv - asset.residual_value)
        if dep <= 0:
            break

        accum += dep
        rows.append({
            'year': year,
            'opening_nbv': nbv,
            'depreciation': dep,
            'closing_nbv': nbv - dep,
            'accumulated': accum,
        })
        nbv -= dep

    return rows
