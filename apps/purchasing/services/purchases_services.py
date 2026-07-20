import nepali_datetime
from django.db import transaction
from django.db.models import Max

from apps.company.models import Company, FiscalYear


def generate_po_number(company_id) -> tuple:
    """
    Format: {COMPANY}-PO-{FY}-{NNNN}, e.g. DPS-PO-2082/83-0001

    Sequential and scoped to the active fiscal year — mirrors
    apps.billing.services.invoice_service.generate_invoice_number so the
    sequence resets per fiscal year and continues from that fiscal year's
    last number when you switch back to it.
    Returns (purchase_order_number, sequence, fiscal_year).
    """
    from apps.purchasing.models import PurchaseOrder

    today_np = nepali_datetime.date.today()
    fiscal_year = None
    try:
        company = Company.active_objects.get(id=company_id)
        company_prefix = company.name[:3].upper().strip().ljust(3, 'X')
        fiscal_year = FiscalYear.active_objects.filter(is_active=True, company=company).first()
        fiscal_year_name = fiscal_year.name if fiscal_year else today_np.strftime("%y/%m/%d")
    except (Company.DoesNotExist, AttributeError):
        company_prefix = "PO"
        fiscal_year_name = today_np.strftime("%y/%m/%d")

    prefix = f"{company_prefix}-PO-{fiscal_year_name}-"

    with transaction.atomic():
        fy_filter = {'fiscal_year': fiscal_year} if fiscal_year else {'fiscal_year__isnull': True}
        last_seq = PurchaseOrder.objects.select_for_update().filter(
            company_id=company_id, **fy_filter,
        ).aggregate(max_seq=Max('sequence_number'))['max_seq'] or 0

        sequence = last_seq + 1
        po_number = f"{prefix}{sequence:04d}"
        while PurchaseOrder.objects.filter(purchase_order_number=po_number).exists():
            sequence += 1
            po_number = f"{prefix}{sequence:04d}"

    return po_number, sequence, fiscal_year