from django.core.management.base import BaseCommand
from django.db import transaction

from apps.company.models import Company, FiscalYear
from apps.orders.models import SalesOrder, DeliveryNote
from apps.restaurant.models import DiningOrder
from apps.tours.models import TourEnquiry, TourBooking
from apps.hrpayroll.models import PayrollRun
from apps.manufacturing.models import WorkOrder
from apps.ecom.models import EcomOrder

# (model, date_field_to_match_against_fiscal_year)
# date_field=None means fall back to created_at.date()
_MODELS = [
    (SalesOrder, 'order_date'),
    (DeliveryNote, 'dispatch_date'),
    (DiningOrder, None),
    (TourEnquiry, None),
    (TourBooking, 'travel_date'),
    (PayrollRun, 'payroll_date'),
    (WorkOrder, None),
    (EcomOrder, None),
]


def find_fiscal_year(fiscal_years, doc_date):
    for fy in fiscal_years:
        if fy.start_date <= doc_date <= fy.end_date:
            return fy
    return None


class Command(BaseCommand):
    help = (
        "Backfill fiscal_year and sequence_number on document rows created "
        "before this session's numbering fix (SalesOrder, DeliveryNote, "
        "DiningOrder, TourEnquiry, TourBooking, PayrollRun, WorkOrder, "
        "EcomOrder). Matches each row's date field to a fiscal year and "
        "assigns sequence_number in created_at order within that fiscal "
        "year. Cosmetic only — never touches the existing document number "
        "string (order_number, delivery_number, etc. stay exactly as "
        "issued). Dry-run by default — pass --apply to write."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply', action='store_true',
            help='Actually write fiscal_year/sequence_number. Without this flag, only reports what would change.',
        )

    def handle(self, *args, **options):
        apply_changes = options['apply']

        for model, date_field in _MODELS:
            for company in Company.objects.all():
                fiscal_years = list(FiscalYear.objects.filter(company=company).order_by('start_date'))
                if not fiscal_years:
                    continue

                qs = model.objects.filter(company=company, fiscal_year__isnull=True).order_by('created_at')
                unmatched = 0
                changed = 0
                # Track next sequence per fiscal year as we assign them in order
                next_seq = {}

                with transaction.atomic():
                    for row in qs:
                        doc_date = getattr(row, date_field) if date_field else None
                        if doc_date is None:
                            doc_date = row.created_at.date()

                        fy = find_fiscal_year(fiscal_years, doc_date)
                        if not fy:
                            unmatched += 1
                            continue

                        seq = next_seq.get(fy.id)
                        if seq is None:
                            last = model.objects.filter(
                                company=company, fiscal_year=fy
                            ).order_by('-sequence_number').first()
                            seq = (last.sequence_number if last and last.sequence_number else 0) + 1
                        else:
                            seq += 1
                        next_seq[fy.id] = seq

                        self.stdout.write(
                            f"[{company.name}] {model.__name__} {row.pk}: "
                            f"date={doc_date} -> fiscal_year={fy.name} sequence_number={seq}"
                        )
                        if not apply_changes:
                            continue
                        row.fiscal_year = fy
                        row.sequence_number = seq
                        row.save(update_fields=['fiscal_year', 'sequence_number'])
                        changed += 1

                    if not apply_changes:
                        transaction.set_rollback(True)

                if changed or unmatched:
                    if unmatched:
                        self.stdout.write(self.style.WARNING(
                            f"[{company.name}] {model.__name__}: {unmatched} row(s) have a date "
                            f"outside any known fiscal year — left unchanged."
                        ))
                    self.stdout.write(self.style.SUCCESS(
                        f"[{company.name}] {model.__name__}: {changed} row(s) "
                        f"{'would be ' if not apply_changes else ''}backfilled."
                    ))

        if not apply_changes:
            self.stdout.write(self.style.WARNING(
                "\nDry run — nothing was written. Re-run with --apply to write these."
            ))
