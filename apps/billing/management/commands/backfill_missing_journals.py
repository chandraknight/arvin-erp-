from django.core.management.base import BaseCommand
from django.db import transaction

from apps.billing.models import Invoice
from apps.bookkeeping.models import JournalEntry
from apps.payments.models import Payment


class Command(BaseCommand):
    help = (
        "Backfill journal entries for Invoices/Payments that predate the fix "
        "removing the ESTIMATE-status skip in apps/billing/signals.py and the "
        "missing journal_type/source_type/is_cleared columns in "
        "fn_post_invoice_journal/fn_post_payment_journal (migration 0026). "
        "Non-VAT (status=ESTIMATE) invoices created before that fix never "
        "posted a journal entry, and any payment created against them failed "
        "silently the same way. Dry-run by default — pass --apply to write."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply', action='store_true',
            help='Actually post the missing journal entries. Without this flag, only reports what would run.',
        )

    def handle(self, *args, **options):
        apply_changes = options['apply']
        from apps.bookkeeping.db_functions import post_invoice_journal, post_payment_journal

        invoices = Invoice.objects.filter(
            is_deleted=False, total__gt=0,
        ).exclude(status='CANCELLED').select_related('company')

        missing_invoices = []
        for inv in invoices:
            if not inv.invoice_number:
                continue
            has_journal = JournalEntry.objects.filter(
                company=inv.company,
                description=f'Invoice {inv.invoice_number}',
                is_deleted=False,
            ).exists()
            if not has_journal:
                missing_invoices.append(inv)

        self.stdout.write(f"Found {len(missing_invoices)} invoice(s) with no journal entry.")
        for inv in missing_invoices:
            self.stdout.write(
                f"  [{inv.company.name if inv.company else '?'}] {inv.invoice_number} "
                f"status={inv.status} total={inv.total}"
            )

        posted_invoices = 0
        if apply_changes:
            for inv in missing_invoices:
                try:
                    with transaction.atomic():
                        post_invoice_journal(inv.id)
                    posted_invoices += 1
                except Exception as exc:
                    self.stdout.write(self.style.ERROR(
                        f"  FAILED invoice {inv.invoice_number}: {exc}"
                    ))

        missing_payments = list(
            Payment.objects.filter(is_deleted=False, journal_entry__isnull=True)
            .select_related('company', 'invoice')
        )

        self.stdout.write(f"\nFound {len(missing_payments)} payment(s) with no journal entry.")
        for pay in missing_payments:
            self.stdout.write(
                f"  [{pay.company.name if pay.company else '?'}] "
                f"payment={pay.id} invoice={pay.invoice.invoice_number if pay.invoice else '-'} "
                f"amount={pay.amount} method={pay.method}"
            )

        posted_payments = 0
        if apply_changes:
            for pay in missing_payments:
                try:
                    with transaction.atomic():
                        post_payment_journal(pay.id)
                    posted_payments += 1
                except Exception as exc:
                    self.stdout.write(self.style.ERROR(
                        f"  FAILED payment {pay.id}: {exc}"
                    ))

        if apply_changes:
            self.stdout.write(self.style.SUCCESS(
                f"\nPosted {posted_invoices}/{len(missing_invoices)} invoice journal(s), "
                f"{posted_payments}/{len(missing_payments)} payment journal(s)."
            ))
        else:
            self.stdout.write(self.style.WARNING(
                "\nDry run — no journals were posted. Re-run with --apply to write these."
            ))
