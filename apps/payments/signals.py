from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import DatabaseError
import logging

from apps.bookkeeping.models import LedgerAccount, JournalEntry, JournalEntryLine
from apps.company.services.company_services import setup_default_ledger_accounts
from apps.payments.models import Payment, VendorPayment

logger = logging.getLogger(__name__)
audit_logger = logging.getLogger("audit")


# ─────────────────────────────────────────────────────────────────────────────
# CUSTOMER / VENDOR / EXPENSE / SALARY / OTHER PAYMENT
# Delegates to fn_post_payment_journal (PostgreSQL).
# Fixes Bug 3: CUSTOMER payments now credit the customer sub-ledger account,
# not the generic Accounts Receivable, so the AR sub-ledger clears correctly.
# ─────────────────────────────────────────────────────────────────────────────
@receiver(post_save, sender=Payment)
def create_journal_entry_for_payment(sender, instance, created, **kwargs):
    if not created:
        return

    # Resolve company from created_by if not set directly
    if not instance.company and instance.created_by and hasattr(instance.created_by, "company"):
        instance.company = instance.created_by.company
        instance.save(update_fields=["company"])

    if not instance.company:
        logger.warning("Payment %s has no company — journal entry skipped", instance.id)
        return

    setup_default_ledger_accounts(instance.company)

    try:
        from apps.bookkeeping.db_functions import post_payment_journal
        journal_entry_id = post_payment_journal(instance.id)
        audit_logger.info(
            "PAYMENT_JOURNALISED payment=%s type=%s amount=%s journal_entry=%s company=%s",
            instance.id, instance.payment_type, instance.amount,
            journal_entry_id, instance.company_id,
        )
    except (DatabaseError, ValueError) as exc:
        logger.error(
            "post_payment_journal failed payment=%s error=%s",
            instance.id, exc,
        )
        raise exc


# ─────────────────────────────────────────────────────────────────────────────
# VENDOR PAYMENT (simpler model — no journal_entry FK, handled inline)
# ─────────────────────────────────────────────────────────────────────────────
@receiver(post_save, sender=VendorPayment)
def create_journal_entry_for_vendor_payment(sender, instance, created, **kwargs):
    if not created:
        return

    company = (
        instance.vendor_bill.purchase_order.company
        if instance.vendor_bill.purchase_order
        else instance.vendor_bill.vendor.company
    )

    # Assign a sequential reference number if not already set
    if not instance.reference_number and company:
        try:
            from apps.payments.services.payment_number_service import generate_payment_number
            from django.db.models import Max
            # VendorPayment uses its own sequence scoped to company
            last_seq = (
                VendorPayment.objects
                .select_for_update()
                .filter(vendor_bill__vendor__company=company)
                .exclude(reference_number__isnull=True)
                .aggregate(max_seq=Max('id'))
            )
            # Use a simple VPY- prefix with count-based sequence
            count = VendorPayment.objects.filter(
                vendor_bill__vendor__company=company
            ).count()
            from apps.company.models import FiscalYear
            import nepali_datetime
            company_prefix = company.name[:3].upper().strip().ljust(3, 'X')
            fy = FiscalYear.active_objects.filter(is_active=True, company=company).first()
            date_part = fy.name if fy else nepali_datetime.date.today().strftime("%y/%m/%d")
            ref = f"{company_prefix}-VPY-{date_part}-{count:04d}"
            VendorPayment.objects.filter(pk=instance.pk).update(reference_number=ref)
            instance.reference_number = ref
        except Exception as exc:
            logger.warning("Could not generate VendorPayment reference: %s", exc)

    setup_default_ledger_accounts(company)

    ap_account = LedgerAccount.objects.filter(
        company=company, name="Accounts Payable", is_deleted=False
    ).first()

    cash_bank = instance.bank_account.ledger_account if instance.bank_account else None
    if not cash_bank:
        if instance.payment_method == "CASH":
            cash_bank = LedgerAccount.objects.filter(
                company=company, name="Cash", is_deleted=False
            ).first()
        else:
            cash_bank = LedgerAccount.objects.filter(
                company=company, name="Bank", is_deleted=False
            ).first()

    if not ap_account or not cash_bank:
        logger.error(
            "Missing AP or Cash/Bank account for company %s — vendor payment %s not journalised",
            company, instance.id,
        )
        return

    entry = JournalEntry.objects.create(
        company=company,
        date=instance.payment_date,
        description=f"Vendor Payment {instance.reference_number or ''} for Bill {instance.vendor_bill.bill_number}".strip(),
    )
    JournalEntryLine.objects.bulk_create([
        JournalEntryLine(journal_entry=entry, account=ap_account, entry_type="DEBIT",  amount=instance.amount),
        JournalEntryLine(journal_entry=entry, account=cash_bank,  entry_type="CREDIT", amount=instance.amount),
    ])

    audit_logger.info(
        "VENDOR_PAYMENT_JOURNALISED vendor_payment=%s bill=%s journal_entry=%s company=%s",
        instance.id, instance.vendor_bill.bill_number, entry.id, company.id,
    )
