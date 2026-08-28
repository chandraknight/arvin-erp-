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
