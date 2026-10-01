from datetime import date as _date, datetime
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.company.models import Company
from apps.products.services.inventory_reconciliation_service import (
    inventory_reconciliation_preview, reconcile_inventory,
)


class Command(BaseCommand):
    help = (
        "Reconcile the ledger Inventory account to the stock valuation (NFRS 2). "
        "Run once per company when adopting the perpetual inventory method, so purchases "
        "that were previously expensed are capitalised. Dry-run unless --apply is given."
    )

    def add_arguments(self, parser):
        parser.add_argument('--company', help='Company id or exact name (default: all companies)')
        parser.add_argument('--as-of', help='AD date YYYY-MM-DD (default: today)')
        parser.add_argument('--apply', action='store_true', help='Post the adjusting entry')

    def handle(self, *args, **opts):
        as_of = datetime.strptime(opts['as_of'], '%Y-%m-%d').date() if opts['as_of'] else _date.today()
        companies = Company.objects.filter(enable_inventory=True)
        if opts['company']:
            c = opts['company']
            matched = companies.filter(name=c)
            if not matched.exists():
                try:
                    matched = companies.filter(pk=c)
                except (ValueError, ValidationError):
                    matched = companies.none()
            companies = matched
            if not companies.exists():
                raise CommandError(f"No inventory-enabled company matches {c!r}")

        for company in companies:
            book, valuation, adj = inventory_reconciliation_preview(company, as_of)
            self.stdout.write(f"{company.name}: ledger={book} valuation={valuation} adjustment={adj}")
            if adj == Decimal('0.00') or not opts['apply']:
                continue
            try:
                entry = reconcile_inventory(company, as_of)
                self.stdout.write(self.style.SUCCESS(f"  posted {entry.voucher_no}"))
            except ValueError as exc:
                self.stdout.write(self.style.WARNING(f"  skipped: {exc}"))
