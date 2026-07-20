from django.core.management.base import BaseCommand
from django.db import transaction

from apps.billing.models import CreditNote, DebitNote
from apps.company.models import Company, FiscalYear
from apps.purchasing.models import PurchaseOrder


def company_prefix(company):
    return company.name[:3].upper().strip().ljust(3, 'X')


def find_fiscal_year(fiscal_years, doc_date):
    for fy in fiscal_years:
        if fy.start_date <= doc_date <= fy.end_date:
            return fy
    return None


class Command(BaseCommand):
    help = (
        "Renumber existing Credit Notes, Debit Notes, and Purchase Orders "
        "created before fiscal-year-scoped sequential numbering was added, "
        "so their numbers follow the same {COMPANY}-{TYPE}-{FY}-{NNNN} "
        "pattern as new documents. Assigns fiscal_year + sequence_number "
        "ordered chronologically within each fiscal year."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Show what would change without writing to the database.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        for company in Company.objects.all():
            fiscal_years = list(FiscalYear.objects.filter(company=company).order_by('start_date'))
            if not fiscal_years:
                continue

            prefix_base = company_prefix(company)

            self._backfill(
                company, fiscal_years, prefix_base, dry_run,
                queryset=CreditNote.objects.filter(company=company, sequence_number__isnull=True).order_by('created_at'),
                date_field=lambda obj: obj.created_at.date(),
                doc_type='CN',
                number_field='credit_note_number',
                label='Credit Note',
            )
            self._backfill(
                company, fiscal_years, prefix_base, dry_run,
                queryset=DebitNote.objects.filter(company=company, sequence_number__isnull=True).order_by('created_at'),
                date_field=lambda obj: obj.created_at.date(),
                doc_type='DN',
                number_field='debit_note_number',
                label='Debit Note',
            )
            self._backfill(
                company, fiscal_years, prefix_base, dry_run,
                queryset=PurchaseOrder.objects.filter(company=company, sequence_number__isnull=True).order_by('date', 'created_at'),
                date_field=lambda obj: obj.date,
                doc_type='PO',
                number_field='purchase_order_number',
                label='Purchase Order',
            )

    def _backfill(self, company, fiscal_years, prefix_base, dry_run, queryset, date_field, doc_type, number_field, label):
        # Running per-fiscal-year sequence counters, seeded from any records
        # already numbered under the new scheme (e.g. created after the
        # numbering fix went live).
        model = queryset.model
        counters = {}
        for fy in fiscal_years:
            last = model.objects.filter(company=company, fiscal_year=fy).order_by('-sequence_number').first()
            counters[fy.id] = last.sequence_number if (last and last.sequence_number) else 0

        unmatched = 0
        changed = 0

        with transaction.atomic():
            for obj in queryset:
                doc_date = date_field(obj)
                fy = find_fiscal_year(fiscal_years, doc_date)
                if not fy:
                    unmatched += 1
                    continue

                counters[fy.id] += 1
                sequence = counters[fy.id]
                new_number = f"{prefix_base}-{doc_type}-{fy.name}-{sequence:04d}"
                old_number = getattr(obj, number_field)

                self.stdout.write(
                    f"[{company.name}] {label}: {old_number!r} -> {new_number!r} (FY {fy.name}, seq {sequence})"
                )

                if not dry_run:
                    setattr(obj, number_field, new_number)
                    obj.sequence_number = sequence
                    obj.fiscal_year = fy
                    obj.save(update_fields=[number_field, 'sequence_number', 'fiscal_year'])
                changed += 1

            if dry_run:
                transaction.set_rollback(True)

        if unmatched:
            self.stdout.write(self.style.WARNING(
                f"[{company.name}] {label}: {unmatched} record(s) have a date outside any known fiscal year — left unchanged."
            ))
        self.stdout.write(self.style.SUCCESS(
            f"[{company.name}] {label}: {changed} record(s) {'would be ' if dry_run else ''}renumbered."
        ))
