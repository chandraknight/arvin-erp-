"""
Nepal payroll tax calculations — income tax slabs and SSF contributions.

calculate_income_tax(): NOTE — Nepal income tax slabs/rates change every
fiscal year per the Finance Act. Configure apps.hrpayroll.models.IncomeTaxSlab
per company/fiscal year (see get_or_create_default_slabs) and have an
accountant verify the figures before running production payroll.
"""
import logging
from decimal import Decimal

logger = logging.getLogger(__name__)

SSF_EMPLOYEE_RATE = Decimal('11.00')
SSF_EMPLOYER_RATE = Decimal('20.00')


def calculate_income_tax(annual_taxable_income, marital_status, company, fiscal_year):
    from apps.hrpayroll.models import IncomeTaxSlab

    slabs = IncomeTaxSlab.objects.filter(
        company=company, fiscal_year=fiscal_year, marital_status=marital_status,
    ).order_by('slab_order')

    if not slabs.exists():
        logger.warning(
            "No IncomeTaxSlab configured for company=%s fiscal_year=%s marital_status=%s — "
            "income tax not calculated.", company, fiscal_year, marital_status,
        )
        return Decimal('0.00')

    tax = Decimal('0.00')
    remaining = Decimal(str(annual_taxable_income))
    lower_bound = Decimal('0.00')

    for slab in slabs:
        if remaining <= Decimal('0.00'):
            break
        band_width = (slab.upper_limit - lower_bound) if slab.upper_limit is not None else remaining
        taxable_in_band = min(remaining, band_width)
        tax += taxable_in_band * slab.rate / Decimal('100')
        remaining -= taxable_in_band
        lower_bound = slab.upper_limit if slab.upper_limit is not None else lower_bound

    return tax.quantize(Decimal('0.01'))


def calculate_ssf(basic_salary):
    basic_salary = Decimal(str(basic_salary))
    employee_amount = (basic_salary * SSF_EMPLOYEE_RATE / Decimal('100')).quantize(Decimal('0.01'))
    employer_amount = (basic_salary * SSF_EMPLOYER_RATE / Decimal('100')).quantize(Decimal('0.01'))
    return employee_amount, employer_amount


def get_or_create_default_slabs(company, fiscal_year):
    """
    Seed approximate current Nepal income tax slabs. Finance-Act-dependent —
    an accountant must review and correct these figures for the active
    fiscal year before payroll relying on them goes live.
    """
    from apps.hrpayroll.models import IncomeTaxSlab

    if IncomeTaxSlab.objects.filter(company=company, fiscal_year=fiscal_year).exists():
        return IncomeTaxSlab.objects.filter(company=company, fiscal_year=fiscal_year)

    slab_defs = {
        'SINGLE': [
            (Decimal('500000'), Decimal('1.00')),
            (Decimal('700000'), Decimal('10.00')),
            (Decimal('1000000'), Decimal('20.00')),
            (Decimal('2000000'), Decimal('30.00')),
            (None, Decimal('36.00')),
        ],
        'MARRIED': [
            (Decimal('600000'), Decimal('1.00')),
            (Decimal('800000'), Decimal('10.00')),
            (Decimal('1100000'), Decimal('20.00')),
            (Decimal('2100000'), Decimal('30.00')),
            (None, Decimal('36.00')),
        ],
    }

    created = []
    for marital_status, bands in slab_defs.items():
        for order, (upper_limit, rate) in enumerate(bands, start=1):
            slab, _ = IncomeTaxSlab.objects.get_or_create(
                company=company, fiscal_year=fiscal_year,
                marital_status=marital_status, slab_order=order,
                defaults={'upper_limit': upper_limit, 'rate': rate},
            )
            created.append(slab)
    return created
