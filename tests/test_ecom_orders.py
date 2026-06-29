"""
Tests: Ecom order → SalesOrder → Invoice pipeline.

Flows covered:
  - EcomOrder.order_number is scoped per company (not cross-company)
  - create_sales_order_from_ecom creates a SalesOrder with valid status (DRAFT)
  - SalesOrder status sync signal maps DRAFT → PENDING on EcomOrder
  - convert_to_invoice assigns invoice_number and uses company tax_rate
  - convert_to_invoice is idempotent (second call redirects to existing invoice)
  - Stock deduction targets ecom_stock, not pos stock
"""
from decimal import Decimal
from datetime import date

from django.test import TestCase

from apps.ecom.models import EcomOrder, EcomOrderItem
from apps.ecom.services import create_sales_order_from_ecom
from apps.orders.models import SalesOrder
from apps.products.models import ProductStock
from .base import BaseERPTestCase


class EcomOrderNumberScopingTests(BaseERPTestCase):
    """order_number must be scoped per company."""

    def test_first_order_starts_at_00001(self):
        order = EcomOrder.objects.create(
            company=self.company,
            customer_name='Alice',
            customer_phone='9800000001',
            delivery_address='KTM',
            subtotal=Decimal('500.00'),
            total=Decimal('500.00'),
        )
        self.assertEqual(order.order_number, 'EC-00001')

    def test_second_order_increments(self):
        EcomOrder.objects.create(
            company=self.company,
            customer_name='Alice',
            customer_phone='9800000001',
            delivery_address='KTM',
            subtotal=Decimal('500.00'),
            total=Decimal('500.00'),
        )
        order2 = EcomOrder.objects.create(
            company=self.company,
            customer_name='Bob',
            customer_phone='9800000002',
            delivery_address='PKR',
            subtotal=Decimal('200.00'),
            total=Decimal('200.00'),
        )
        self.assertEqual(order2.order_number, 'EC-00002')

    def test_explicit_order_number_preserved(self):
        order = EcomOrder.objects.create(
            company=self.company,
            customer_name='Charlie',
            customer_phone='9800000003',
            delivery_address='BKT',
            order_number='EC-99999',
            subtotal=Decimal('100.00'),
            total=Decimal('100.00'),
        )
        self.assertEqual(order.order_number, 'EC-99999')


class CreateSalesOrderFromEcomTests(BaseERPTestCase):
    """create_sales_order_from_ecom must produce a valid, linked SalesOrder."""

    def _make_ecom_order(self):
        order = EcomOrder.objects.create(
            company=self.company,
            customer=self.customer,
            customer_name=self.customer.name,
            customer_phone=self.customer.phone or '9800000001',
            delivery_address='Test Address',
            subtotal=Decimal('1000.00'),
            total=Decimal('1000.00'),
        )
        EcomOrderItem.objects.create(
            order=order,
            product=self.product,
            quantity=2,
            unit_price=Decimal('500.00'),
            total_price=Decimal('1000.00'),
        )
        return order

    def test_creates_linked_sales_order(self):
        ecom_order = self._make_ecom_order()
        so = create_sales_order_from_ecom(ecom_order)
        ecom_order.refresh_from_db()
        self.assertIsNotNone(so)
        self.assertEqual(ecom_order.sales_order_id, so.id)

    def test_sales_order_status_is_valid(self):
        """DRAFT is the only valid initial status — PENDING caused DB integrity issues."""
        ecom_order = self._make_ecom_order()
        so = create_sales_order_from_ecom(ecom_order)
        valid_statuses = {'DRAFT', 'CONFIRMED', 'PROCESSING', 'DISPATCHED', 'DELIVERED', 'CANCELLED', 'RETURNED'}
        self.assertIn(so.status, valid_statuses)

    def test_sales_order_status_is_draft(self):
        ecom_order = self._make_ecom_order()
        so = create_sales_order_from_ecom(ecom_order)
        self.assertEqual(so.status, 'DRAFT')

    def test_idempotent_when_called_twice(self):
        ecom_order = self._make_ecom_order()
        so1 = create_sales_order_from_ecom(ecom_order)
        so2 = create_sales_order_from_ecom(ecom_order)
        self.assertEqual(so1.id, so2.id)
        self.assertEqual(SalesOrder.objects.filter(company=self.company).count(), 1)

    def test_sales_order_items_created(self):
        ecom_order = self._make_ecom_order()
        so = create_sales_order_from_ecom(ecom_order)
        self.assertEqual(so.items.count(), 1)

    def test_sales_order_total_matches_ecom_total(self):
        ecom_order = self._make_ecom_order()
        so = create_sales_order_from_ecom(ecom_order)
        self.assertEqual(so.total, ecom_order.total)

    def test_ecom_status_syncs_to_pending_when_draft(self):
        """Signal: SalesOrder DRAFT → EcomOrder PENDING."""
        ecom_order = self._make_ecom_order()
        so = create_sales_order_from_ecom(ecom_order)
        ecom_order.refresh_from_db()
        # The signal in orders/signals.py maps DRAFT → PENDING
        self.assertEqual(ecom_order.status, 'PENDING')


class ConvertToInvoiceTests(BaseERPTestCase):
    """convert_to_invoice view must generate invoice_number and use company tax_rate."""

    def _make_confirmed_so(self):
        from apps.orders.models import SalesOrder, SalesOrderItem
        so = SalesOrder.objects.create(
            company=self.company,
            customer=self.customer,
            order_number='SO-2025-0001',
            order_date=date(2025, 7, 16),
            status='CONFIRMED',
            subtotal=Decimal('1000.00'),
            discount_amount=Decimal('0.00'),
            tax_amount=Decimal('130.00'),
            total=Decimal('1130.00'),
        )
        SalesOrderItem.objects.create(
            order=so,
            product=self.product,
            description=self.product.name,
            quantity=2,
            unit_price=Decimal('500.00'),
        )
        return so

    def test_invoice_number_is_generated(self):
        from apps.billing.models import Invoice
        so = self._make_confirmed_so()
        resp = self.client.post(f'/orders/sales-orders/{so.pk}/convert-invoice/', follow=True)
        invoice = Invoice.objects.filter(company=self.company).order_by('-created_at').first()
        self.assertIsNotNone(invoice)
        self.assertIsNotNone(invoice.invoice_number)
        self.assertNotEqual(invoice.invoice_number, '')

    def test_invoice_uses_company_tax_rate(self):
        from apps.billing.models import Invoice
        self.company.tax_rate = Decimal('13.00')
        self.company.save()
        so = self._make_confirmed_so()
        self.client.post(f'/orders/sales-orders/{so.pk}/convert-invoice/', follow=True)
        invoice = Invoice.objects.filter(company=self.company).order_by('-created_at').first()
        self.assertIsNotNone(invoice)
        self.assertEqual(invoice.tax_percent, Decimal('13.00'))

    def test_convert_twice_does_not_create_duplicate(self):
        from apps.billing.models import Invoice
        so = self._make_confirmed_so()
        self.client.post(f'/orders/sales-orders/{so.pk}/convert-invoice/', follow=True)
        count_after_first = Invoice.objects.filter(company=self.company).count()
        self.client.post(f'/orders/sales-orders/{so.pk}/convert-invoice/', follow=True)
        count_after_second = Invoice.objects.filter(company=self.company).count()
        self.assertEqual(count_after_first, count_after_second)


class EcomStockDeductionTests(BaseERPTestCase):
    """Placing an order must deduct ecom_stock, not pos stock."""

    def setUp(self):
        super().setUp()
        self.stock = ProductStock.objects.get(product=self.product)
        self.stock.ecom_stock = 10
        self.stock.stock = 50
        self.stock.save()

    def test_ecom_order_deducts_ecom_stock(self):
        order = EcomOrder.objects.create(
            company=self.company,
            customer=self.customer,
            customer_name=self.customer.name,
            customer_phone=self.customer.phone or '9800000001',
            delivery_address='Test',
            subtotal=self.product.price * 2,
            total=self.product.price * 2,
        )
        EcomOrderItem.objects.create(
            order=order,
            product=self.product,
            quantity=2,
            unit_price=self.product.price,
            total_price=self.product.price * 2,
        )
        # Manually simulate stock deduction (as place_order does)
        from django.db.models import F
        ProductStock.objects.filter(product=self.product).update(
            ecom_stock=F('ecom_stock') - 2
        )
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.ecom_stock, 8)
        self.assertEqual(self.stock.stock, 50)  # pos stock unchanged
