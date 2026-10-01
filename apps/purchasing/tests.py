from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.company.models import Company
from apps.vendors.models import Vendor
from apps.purchasing.models import PurchaseOrder
from apps.purchasing.services.approval_services import evaluate_approval_requirement


class EvaluateApprovalRequirementTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Test Co')
        self.vendor = Vendor.objects.create(company=self.company, name='Test Vendor')

    def _make_po(self, total_amount):
        return PurchaseOrder.objects.create(
            company=self.company,
            vendor=self.vendor,
            total_amount=Decimal(total_amount),
        )

    def test_above_threshold_requires_approval(self):
        self.company.po_approval_threshold = Decimal('1000.00')
        po = self._make_po('1500.00')
        evaluate_approval_requirement(po)
        self.assertEqual(po.approval_status, 'PENDING')

    def test_at_threshold_requires_approval(self):
        self.company.po_approval_threshold = Decimal('1000.00')
        po = self._make_po('1000.00')
        evaluate_approval_requirement(po)
        self.assertEqual(po.approval_status, 'PENDING')

    def test_below_threshold_does_not_require_approval(self):
        self.company.po_approval_threshold = Decimal('1000.00')
        po = self._make_po('500.00')
        evaluate_approval_requirement(po)
        self.assertEqual(po.approval_status, 'NOT_REQUIRED')

    def test_null_threshold_never_requires_approval(self):
        self.company.po_approval_threshold = None
        po = self._make_po('999999.00')
        evaluate_approval_requirement(po)
        self.assertEqual(po.approval_status, 'NOT_REQUIRED')

    def test_above_threshold_sets_status_draft(self):
        self.company.po_approval_threshold = Decimal('1000.00')
        po = self._make_po('1500.00')
        evaluate_approval_requirement(po)
        self.assertEqual(po.status, 'DRAFT')


class GoodsReceivedNotInvoicedTests(TestCase):
    """Receipt posts DR Inventory / CR GRNI; the later bill clears GRNI (no double count)."""

    def setUp(self):
        from apps.company.models import Company
        from apps.products.models import Category, Product
        from apps.vendors.models import Vendor
        from apps.purchasing.models import PurchaseOrder, PurchaseOrderItem
        self.company = Company.objects.create(name="GRN Co", enable_inventory=True)
        cat = Category.objects.create(company=self.company, name="Cat")
        self.product = Product.objects.create(
            company=self.company, name="Widget", category=cat, price=Decimal('100'), cost_price=Decimal('10'))
        self.vendor = Vendor.objects.create(company=self.company, name="Vend")
        self.po = PurchaseOrder.objects.create(
            company=self.company, vendor=self.vendor, purchase_order_number="GRN-PO-1", status='RECEIVED')
        PurchaseOrderItem.objects.create(
            purchase_order=self.po, item_type='STOCK', product=self.product, quantity=10, price=Decimal('10'))

    def _balances(self):
        from apps.bookkeeping.models import JournalEntryLine
        out = {}
        for l in JournalEntryLine.objects.filter(journal_entry__company=self.company):
            sign = 1 if l.entry_type == 'DEBIT' else -1
            out[l.account.name] = out.get(l.account.name, Decimal('0')) + sign * l.amount
        return out

    def test_receipt_posts_dr_inventory_cr_grni_once(self):
        from apps.purchasing.services.grn_service import post_goods_received_journal
        entry = post_goods_received_journal(self.po)
        self.assertEqual(entry.source_type, 'GRN')
        self.assertEqual(self._balances()['Inventory'], Decimal('100.00'))
        self.assertEqual(self._balances()['Goods Received Not Invoiced'], Decimal('-100.00'))
        self.assertIsNone(post_goods_received_journal(self.po))  # idempotent

    def test_bill_after_receipt_clears_grni_not_inventory(self):
        from apps.purchasing.services.grn_service import post_goods_received_journal
        from apps.billing.models import VendorBill, VendorBillItem
        from apps.bookkeeping.models import get_or_create_system_account
        post_goods_received_journal(self.po)
        bill = VendorBill(company=self.company, vendor=self.vendor, purchase_order=self.po,
                          bill_number="B-1", bill_date=date.today(), due_date=date.today())
        bill._skip_journal = True
        bill.save()
        expense = get_or_create_system_account(self.company, "Purchase Expense", "EXPENSE", code="5000")
        VendorBillItem.objects.create(vendor_bill=bill, product=self.product, quantity=10,
                                      price=Decimal('10'), debit_account=expense)
        bill._skip_journal = False
        bill.save(update_fields=['total_amount'])
        bal = self._balances()
        self.assertEqual(bal['Inventory'], Decimal('100.00'))            # not doubled
        self.assertEqual(bal.get('Goods Received Not Invoiced', Decimal('0')), Decimal('0.00'))
        self.assertEqual(bal['Accounts Payable'], Decimal('-100.00'))
