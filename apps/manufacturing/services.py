from django.db import transaction
from django.db.models import Max

import nepali_datetime

from apps.company.models import Company, FiscalYear


def generate_work_order_number(company_id):
    """
    Format: {COMPANY_PREFIX}-WO-{FISCAL_YEAR}-{NNNN}, e.g. DPS-WO-2082/83-0001.
    Same fiscal-year-scoped, race-safe pattern as generate_invoice_number.
    Returns (work_order_number, sequence, fiscal_year).
    """
    from apps.manufacturing.models import WorkOrder

    today_np = nepali_datetime.date.today()
    fiscal_year = None
    try:
        company = Company.active_objects.get(id=company_id)
        company_prefix = company.name[:3].upper().strip().ljust(3, 'X')
        fiscal_year = FiscalYear.active_objects.filter(is_active=True, company=company).first()
        fiscal_year_name = fiscal_year.name if fiscal_year else today_np.strftime("%y/%m/%d")
    except (Company.DoesNotExist, AttributeError):
        company_prefix = "WO"
        fiscal_year_name = today_np.strftime("%y/%m/%d")

    prefix = f"{company_prefix}-WO-{fiscal_year_name}-"

    fy_filter = {'fiscal_year': fiscal_year} if fiscal_year else {'fiscal_year__isnull': True}
    with transaction.atomic():
        last_seq = WorkOrder.objects.select_for_update().filter(
            company_id=company_id,
            **fy_filter,
        ).aggregate(max_seq=Max('sequence_number'))

        sequence = (last_seq['max_seq'] or 0) + 1

        work_order_number = f"{prefix}{sequence:04d}"
        while WorkOrder.objects.filter(
            company_id=company_id, fiscal_year=fiscal_year, sequence_number=sequence
        ).exists() or WorkOrder.objects.filter(work_order_number=work_order_number).exists():
            sequence += 1
            work_order_number = f"{prefix}{sequence:04d}"

    return work_order_number, sequence, fiscal_year
