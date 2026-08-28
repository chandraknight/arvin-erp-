"""
Income Tax Act 2058, Schedule 2 — pooled depreciation for tax filing.

Separate from NFRS book depreciation (fixed_asset_service.py). Assets are
grouped into pools A-E; each pool depreciates as one WDV block rather than
asset-by-asset. An asset put into use for more than half the fiscal year
gets the full pool rate on its cost added to the pool; half the year or
less gets half the rate (Income Tax Act sec 2, Schedule 2 para 3).
"""
from decimal import Decimal

from .models import IRD_ASSET_POOL_CHOICES, IRD_POOL_RATES


def pooled_depreciation_schedule(company, fiscal_year) -> list[dict]:
    """
    Return one row per pool (A-D; E is listed separately as it's
    amortized by useful life, not pooled WDV):
      { pool, label, rate, opening_wdv, additions_full, additions_half,
        disposal_proceeds, depreciation_base, depreciation, closing_wdv }
    """
    from .models import FixedAsset

    assets = FixedAsset.objects.filter(
        company=company, is_deleted=False, ird_pool__isnull=False,
    ).exclude(ird_pool='')

    rows = []
    for pool_code, label in IRD_ASSET_POOL_CHOICES:
        if pool_code == 'E':
            continue
        rate = IRD_POOL_RATES[pool_code]
        pool_assets = assets.filter(ird_pool=pool_code)

        opening_wdv = Decimal('0.00')
        additions_full = Decimal('0.00')
        additions_half = Decimal('0.00')
        disposal_proceeds = Decimal('0.00')

        for asset in pool_assets:
            if asset.acquisition_date < fiscal_year.start_date:
                opening_wdv += asset.net_book_value
            elif fiscal_year.start_date <= asset.acquisition_date <= fiscal_year.end_date:
                days_in_use = (fiscal_year.end_date - asset.acquisition_date).days + 1
                fiscal_year_days = (fiscal_year.end_date - fiscal_year.start_date).days + 1
                if days_in_use > fiscal_year_days / 2:
                    additions_full += asset.cost
                else:
                    additions_half += asset.cost

            if asset.status == 'DISPOSED' and asset.disposal_date and \
                    fiscal_year.start_date <= asset.disposal_date <= fiscal_year.end_date:
                disposal_proceeds += asset.net_book_value

        depreciation_base = (
            opening_wdv + additions_full + (additions_half / Decimal('2')) - disposal_proceeds
        )
        depreciation = max(
            (depreciation_base * rate / Decimal('100')).quantize(Decimal('0.01')),
            Decimal('0.00'),
        )
        closing_wdv = opening_wdv + additions_full + additions_half - disposal_proceeds - depreciation

        rows.append({
            'pool': pool_code,
            'label': label,
            'rate': rate,
            'opening_wdv': opening_wdv,
            'additions_full': additions_full,
            'additions_half': additions_half,
            'disposal_proceeds': disposal_proceeds,
            'depreciation_base': depreciation_base,
            'depreciation': depreciation,
            'closing_wdv': closing_wdv,
        })

    return rows
