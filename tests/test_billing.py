"""
Tests: Invoice lifecycle, InvoiceItem totals, CreditNote/DebitNote creation,
VendorBill cancellation.

UAT flows covered:
  - Create draft invoice → add items → totals computed correctly
  - Issue invoice → locked from edits / deletion
  - Cancel invoice → status CANCELLED, reason recorded
  - InvoiceItem discount (percent and amount) calculation
  - CreditNote model creation
  - VendorBill cancel guard
"""
from decimal import Decimal
from datetime import date

from django.test import TestCase

from apps.billing.models import Invoice, InvoiceItem, CreditNote, DebitNote, VendorBill
from apps.bookkeeping.models import LedgerAccount
from apps.vendors.models import Vendor
from .base import BaseERPTestCase


class InvoiceModelTests(BaseERPTestCase):

    def _make_invoice(self, status="DRAFT"):
        return Invoice.objects.create(
            company=self.company,
            customer=self.customer,
            total=Decimal("0.00"),
            status=status,
        )

    def test_draft_invoice_not_locked(self):
        inv = self._make_invoice("DRAFT")
        self.assertFalse(inv.is_locked)

    def test_issued_invoice_is_locked(self):
        inv = self._make_invoice("ISSUED")
        self.assertTrue(inv.is_locked)

    def test_cancelled_invoice_is_locked(self):
        inv = self._make_invoice("CANCELLED")
        self.assertTrue(inv.is_locked)

    def test_cancel_sets_status_and_reason(self):
        inv = self._make_invoice("ISSUED")
        inv.cancel(cancelled_by=self.user, reason="Wrong customer")
        inv.refresh_from_db()
        self.assertEqual(inv.status, "CANCELLED")
        self.assertEqual(inv.cancellation_reason, "Wrong customer")

    def test_cancel_already_cancelled_raises(self):
        inv = self._make_invoice("CANCELLED")
        with self.assertRaises(ValueError):
            inv.cancel(cancelled_by=self.user)

    def test_is_paid_when_balance_zero(self):
        inv = self._make_invoice()
        inv.outstanding_balance = Decimal("0.00")
        self.assertTrue(inv.is_paid)

    def test_is_paid_false_when_balance_nonzero(self):
        inv = self._make_invoice()
        inv.outstanding_balance = Decimal("100.00")
        self.assertFalse(inv.is_paid)

    def test_str_uses_invoice_number_when_set(self):
        inv = self._make_invoice()
        inv.invoice_number = "INV-001"
        self.assertIn("INV-001", str(inv))

    def test_is_estimate_flag(self):
        inv = self._make_invoice("ESTIMATE")
        self.assertTrue(inv.is_estimate)
        self.assertFalse(inv.is_issued)


class InvoiceItemTotalTests(BaseERPTestCase):

    def _invoice_with_item(self, qty, price, discount_percent=0, discount_amount=0):
        inv = Invoice.objects.create(
            company=self.company,
            customer=self.customer,
            total=Decimal("0.00"),
        )
        item = InvoiceItem(
            invoice=inv,
            product=self.product,
            quantity=qty,
            price=Decimal(str(price)),
            discount_percent=Decimal(str(discount_percent)),
            discount_amount=Decimal(str(discount_amount)),
        )
        return item

    def test_total_price_no_discount(self):
        item = self._invoice_with_item(2, "500.00")
        self.assertEqual(item.total_price, Decimal("1000.00"))

    def test_total_price_with_percent_discount(self):
        item = self._invoice_with_item(2, "500.00", discount_percent=10)
        # 2 * 500 = 1000, 10% off = 900
        self.assertEqual(item.total_price, Decimal("900.00"))

    def test_total_price_with_amount_discount(self):
        item = self._invoice_with_item(2, "500.00", discount_amount=50)
        # 1000 - 50 = 950
        self.assertEqual(item.total_price, Decimal("950.00"))

    def test_amount_discount_takes_precedence_over_percent(self):
        # When both are set, discount_amount wins (see model logic)
        item = self._invoice_with_item(1, "1000.00", discount_percent=10, discount_amount=100)
        # discount_amount > 0 branch: 1000 - 100 = 900
        self.assertEqual(item.total_price, Decimal("900.00"))

    def test_total_price_never_negative(self):
        item = self._invoice_with_item(1, "10.00", discount_amount=9999)
        self.assertEqual(item.total_price, Decimal("0.00"))

    def test_invoice_totals_sync_on_item_save(self):
        inv = Invoice.objects.create(
            company=self.company,
            customer=self.customer,
            total=Decimal("0.00"),
        )
        InvoiceItem.objects.create(
            invoice=inv,
            product=self.product,
            quantity=2,
            price=Decimal("500.00"),
        )
        inv.refresh_from_db()
        self.assertEqual(inv.subtotal, Decimal("1000.00"))
        self.assertEqual(inv.total, Decimal("1000.00"))

    def test_invoice_totals_sync_on_item_delete(self):
        inv = Invoice.objects.create(
            company=self.company,
            customer=self.customer,
            total=Decimal("0.00"),
        )
        item = InvoiceItem.objects.create(
            invoice=inv,
            product=self.product,
            quantity=1,
            price=Decimal("300.00"),
        )
        item.delete()
        inv.refresh_from_db()
        self.assertEqual(inv.subtotal, Decimal("0.00"))
        self.assertEqual(inv.total, Decimal("0.00"))


class CreditDebitNoteModelTests(BaseERPTestCase):

    def test_credit_note_creation(self):
        inv = Invoice.objects.create(
            company=self.company,
            customer=self.customer,
            total=Decimal("500.00"),
            status="ISSUED",
        )
        cn = CreditNote.objects.create(
            company=self.company,
            invoice=inv,
            customer=self.customer,
            amount=Decimal("500.00"),
            reason="Return",
            status="DRAFT",
        )
        self.assertIsNotNone(cn.pk)
        self.assertEqual(cn.amount, Decimal("500.00"))

    def test_debit_note_creation(self):
        inv = Invoice.objects.create(
            company=self.company,
            customer=self.customer,
            total=Decimal("500.00"),
            status="ISSUED",
        )
        dn = DebitNote.objects.create(
            company=self.company,
            invoice=inv,
            customer=self.customer,
            amount=Decimal("100.00"),
            reason="Additional charge",
            status="DRAFT",
        )
        self.assertIsNotNone(dn.pk)


class VendorBillModelTests(BaseERPTestCase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.vendor = Vendor.objects.create(
            company=cls.company,
            name="Supplier Co",
        )

    def _make_bill(self, status="UNPAID"):
        return VendorBill.objects.create(
            vendor=self.vendor,
            company=self.company,
            bill_number=f"BILL-{status}-001",
            bill_date=date.today(),
            total_amount=Decimal("5000.00"),
            status=status,
        )

    def test_unpaid_bill_not_locked(self):
        bill = self._make_bill("UNPAID")
        self.assertFalse(bill.is_locked)

    def test_paid_bill_is_locked(self):
        bill = self._make_bill("PAID")
        self.assertTrue(bill.is_locked)

    def test_cancel_bill_sets_status(self):
        bill = self._make_bill("UNPAID")
        bill.cancel(cancelled_by=self.user, reason="Duplicate")
        bill.refresh_from_db()
        self.assertEqual(bill.status, "CANCELLED")
        self.assertEqual(bill.cancellation_reason, "Duplicate")

    def test_cancel_already_cancelled_raises(self):
        bill = self._make_bill("CANCELLED")
        with self.assertRaises(ValueError):
            bill.cancel(cancelled_by=self.user)
