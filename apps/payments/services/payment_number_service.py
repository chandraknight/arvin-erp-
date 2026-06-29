import nepali_datetime
from apps.company.models import Company, FiscalYear


def generate_payment_number(company_id, payment_type='CUSTOMER'):
    """
    Race-safe sequential payment number generator.
    Uses select_for_update() inside an atomic block so concurrent requests
    cannot read the same max sequence and generate duplicate numbers.
    Returns (reference_number, sequence) tuple.
    """
    from django.db import transaction
    from django.db.models import Max
    from apps.payments.models import Payment

    today_np = nepali_datetime.date.today()

    try:
        company = Company.active_objects.get(id=company_id)
        company_prefix = company.name[:3].upper().strip().ljust(3, 'X')
        fiscal_year = FiscalYear.active_objects.filter(is_active=True, company=company).first()
        date_part = fiscal_year.name if fiscal_year else today_np.strftime("%y/%m/%d")
    except (Company.DoesNotExist, AttributeError):
        company_prefix = "PAY"
        date_part = today_np.strftime("%y/%m/%d")

    type_prefix = {
        'CUSTOMER': 'REC',
        'VENDOR':   'VPY',
        'EXPENSE':  'EXP',
        'SALARY':   'SAL',
        'OTHER':    'OTH',
    }.get(payment_type, 'PAY')

    prefix = f"{company_prefix}-{type_prefix}-{date_part}-"

    with transaction.atomic():
        if payment_type == 'EXPENSE':
            # Expenses live in a separate table — sequence from Expense.reference_number
            from apps.payments.models import Expense
            last_seq = (
                Expense.objects
                .select_for_update()
                .filter(company_id=company_id, reference_number__startswith=prefix)
                .count()
            )
            sequence = last_seq + 1
            payment_number = f"{prefix}{sequence:04d}"
            while Expense.objects.filter(company_id=company_id,
                                         reference_number=payment_number).exists():
                sequence += 1
                payment_number = f"{prefix}{sequence:04d}"
        else:
            # All other types use the Payment table
            last_seq = (
                Payment.objects
                .select_for_update()
                .filter(company_id=company_id, payment_type=payment_type,
                        reference_number__startswith=prefix)
                .aggregate(max_seq=Max('sequence_number'))
            )['max_seq'] or 0

            sequence = last_seq + 1
            payment_number = f"{prefix}{sequence:04d}"

            while Payment.objects.filter(company_id=company_id,
                                         reference_number=payment_number).exists():
                sequence += 1
                payment_number = f"{prefix}{sequence:04d}"

    return payment_number, sequence
