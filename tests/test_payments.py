"""
Tests: Payment recording, cancellation, outstanding balance restoration.

UAT flows covered:
  - Payment cancels correctly (soft-delete)
  - Cancelled payment restores invoice outstanding_balance
  - Double-cancel raises ValueError
  - Payment str() representation
"""
from decimal import Decimal
from datetime import date

from apps.billing.models import Invoice
from apps.payments.models import Payment, BankAccount
from .base import BaseERPTestCase


class PaymentModelTests(BaseERPTestCase):

    def _make_invoice(self, total=Decimal("1000.00")):
        inv = Invoice.objects.create(
            company=self.company,
            customer=self.customer,
            total=total,
            outstanding_balance=total,
            status="ISSUED",
        )
        return inv

    def _make_payment(self, invoice, amount):
        return Payment.objects.create(
            company=self.company,
            invoice=invoice,
            date=date.today(),
            amount=amount,
            amount_applied=amount,
            method="CASH",
            payment_type="CUSTOMER",
        )

    def test_payment_cancel_soft_deletes(self):
        inv = self._make_invoice()
        pmt = self._make_payment(inv, Decimal("1000.00"))
        pmt.cancel(cancelled_by=self.user)
        pmt.refresh_from_db()
        self.assertTrue(pmt.is_deleted)

    def test_payment_cancel_restores_invoice_balance(self):
        inv = self._make_invoice(Decimal("2000.00"))
        # Simulate partial payment already applied
        inv.outstanding_balance = Decimal("1000.00")
        inv.save(update_fields=["outstanding_balance"])
        pmt = self._make_payment(inv, Decimal("1000.00"))
        pmt.cancel(cancelled_by=self.user)
        inv.refresh_from_db()
        self.assertEqual(inv.outstanding_balance, Decimal("2000.00"))

    def test_double_cancel_raises(self):
        inv = self._make_invoice()
        pmt = self._make_payment(inv, Decimal("500.00"))
        pmt.cancel(cancelled_by=self.user)
        with self.assertRaises(ValueError):
            pmt.cancel(cancelled_by=self.user)

    def test_payment_str_with_reference(self):
        inv = self._make_invoice()
        pmt = self._make_payment(inv, Decimal("500.00"))
        pmt.reference_number = "PAY-2025-001"
        self.assertIn("PAY-2025-001", str(pmt))


class BankAccountModelTests(BaseERPTestCase):

    def test_bank_account_auto_creates_ledger(self):
        bank = BankAccount.objects.create(
            company=self.company,
            bank_name="Nepal Bank",
            account_name="Test Corp Account",
            account_number="0012345678",
        )
        self.assertIsNotNone(bank.ledger_account)
        self.assertEqual(bank.ledger_account.account_type, "ASSET")

    def test_bank_account_without_company_raises(self):
        # BankAccount.company FK is non-nullable: accessing self.company with
        # company_id=None raises RelatedObjectDoesNotExist before the ValueError guard.
        from django.core.exceptions import ObjectDoesNotExist
        with self.assertRaises(ObjectDoesNotExist):
            BankAccount.objects.create(
                company=None,
                bank_name="Nepal Bank",
                account_name="Orphan Account",
                account_number="9999999999",
            )
