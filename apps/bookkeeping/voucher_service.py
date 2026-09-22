import nepali_datetime
from django.db import transaction

from apps.company.models import Company


def generate_voucher_no(company_id, fiscal_year) -> str:
    """
    Sequential Journal Voucher number for statutory audit trail.

    Format: {COMPANY}-JV-{FY}-{NNNN}, e.g. DPS-JV-2082/83-0001.
    Sequence resets to 0001 for each new fiscal year, mirroring
    apps.billing.services.invoice_service.generate_invoice_number.
    """
    from .models import JournalEntry

    today_np = nepali_datetime.date.today()
    try:
        company = Company.active_objects.get(id=company_id)
        company_prefix = company.name[:3].upper().strip().ljust(3, 'X')
    except (Company.DoesNotExist, AttributeError):
        company_prefix = "JVX"
    fiscal_year_name = fiscal_year.name if fiscal_year else today_np.strftime("%y/%m/%d")

    prefix = f"{company_prefix}-JV-{fiscal_year_name}-"
    fy_filter = {'fiscal_year': fiscal_year} if fiscal_year else {'fiscal_year__isnull': True}

    with transaction.atomic():
        # sequence isn't stored separately on JournalEntry, so derive it from
        # the count of existing vouchers in this scope.
        sequence = JournalEntry.objects.select_for_update().filter(
            company_id=company_id, **fy_filter,
        ).exclude(voucher_no__isnull=True).count() + 1

        voucher_no = f"{prefix}{sequence:04d}"
        while JournalEntry.objects.filter(voucher_no=voucher_no).exists():
            sequence += 1
            voucher_no = f"{prefix}{sequence:04d}"

    return voucher_no
