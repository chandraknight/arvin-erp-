from django.core.management.base import BaseCommand
from django.db import transaction

from apps.billing.models import Invoice
from apps.company.models import Company, FiscalYear


def find_fiscal_year(fiscal_years, doc_date):
    for fy in fiscal_years:
        if fy.start_date <= doc_date <= fy.end_date:
            return fy
    return None


class Command(BaseCommand):
    help = (
        "Assign fiscal_year to Invoices created before migration "
        "0024_invoice_fiscal_year_sequence added the column. Matches each "
        "invoice to a fiscal year by its transaction_date. Does not touch "
        "invoice_number or sequence_number — existing document numbers are "
        "left exactly as issued."
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

            qs = Invoice.objects.filter(company=company, fiscal_year__isnull=True)
            unmatched = 0
            changed = 0

            with transaction.atomic():
                for inv in qs:
                    fy = find_fiscal_year(fiscal_years, inv.transaction_date)
                    if not fy:
                        unmatched += 1
                        continue

                    self.stdout.write(
                        f"[{company.name}] {inv.invoice_number or '(unnumbered)'}: "
                        f"transaction_date={inv.transaction_date} -> fiscal_year={fy.name}"
                    )
                    if not dry_run:
                        inv.fiscal_year = fy
                        inv.save(update_fields=['fiscal_year'])
                    changed += 1

                if dry_run:
                    transaction.set_rollback(True)

            if changed or unmatched:
                if unmatched:
                    self.stdout.write(self.style.WARNING(
                        f"[{company.name}] {unmatched} invoice(s) have a transaction_date outside any known fiscal year — left unchanged."
                    ))
                self.stdout.write(self.style.SUCCESS(
                    f"[{company.name}] {changed} invoice(s) {'would be ' if dry_run else ''}backfilled."
                ))
