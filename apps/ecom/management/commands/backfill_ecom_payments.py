from django.core.management.base import BaseCommand
from django.db import transaction

from apps.ecom.models import EcomOrder


class Command(BaseCommand):
    help = (
        "Backfill missing Payments for EcomOrders marked paid (cod_status="
        "COLLECTED or payment_status=PAID) before the automatic payment-on-"
        "collection wiring existed, or where it didn't fire for any other "
        "reason. Finds orders whose linked Invoice still shows an "
        "outstanding_balance and creates the missing Payment via the same "
        "record_ecom_payment() service used by the live admin views. "
        "Dry-run by default — pass --apply to write."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply', action='store_true',
            help='Actually create the missing payments. Without this flag, only reports what would run.',
        )

    def handle(self, *args, **options):
        apply_changes = options['apply']
        from apps.ecom.services import record_ecom_payment

        candidates = EcomOrder.objects.filter(
            is_deleted=False,
        ).exclude(
            sales_order__isnull=True,
        ).select_related('sales_order', 'sales_order__invoice', 'company')

        missing = []
        for order in candidates:
            so = order.sales_order
            invoice = so.invoice if so else None
            if not invoice:
                continue
            was_paid = order.cod_status == 'COLLECTED' or order.payment_status == 'PAID'
            if not was_paid:
                continue
            if invoice.outstanding_balance <= 0:
                continue
            missing.append(order)

        self.stdout.write(f"Found {len(missing)} ecom order(s) marked paid with an unpaid Invoice.")
        for order in missing:
            invoice = order.sales_order.invoice
            self.stdout.write(
                f"  [{order.company.name}] {order.order_number} "
                f"method={order.payment_method} cod_status={order.cod_status} "
                f"payment_status={order.payment_status} "
                f"invoice={invoice.invoice_number} outstanding={invoice.outstanding_balance}"
            )

        posted = 0
        if apply_changes:
            for order in missing:
                try:
                    with transaction.atomic():
                        payment = record_ecom_payment(order, order.created_by)
                    if payment:
                        posted += 1
                    else:
                        self.stdout.write(self.style.WARNING(
                            f"  SKIPPED {order.order_number}: record_ecom_payment returned None"
                        ))
                except Exception as exc:
                    self.stdout.write(self.style.ERROR(
                        f"  FAILED {order.order_number}: {exc}"
                    ))

        if apply_changes:
            self.stdout.write(self.style.SUCCESS(
                f"\nPosted {posted}/{len(missing)} payment(s)."
            ))
        else:
            self.stdout.write(self.style.WARNING(
                "\nDry run — no payments were created. Re-run with --apply to write these."
            ))
