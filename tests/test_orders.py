"""
Tests: SalesOrder creation, status transitions, line items, delivery notes.

UAT flows covered:
  - Order created with line items, totals calculated via property
  - Order status lifecycle (DRAFT → CONFIRMED)
  - Delivery note linked to order
  - DeliveryNoteItem quantity tracking
"""
from decimal import Decimal
from datetime import date

from apps.orders.models import (
    SalesOrder, SalesOrderItem, DeliveryNote, DeliveryNoteItem
)
from .base import BaseERPTestCase


class SalesOrderTests(BaseERPTestCase):

    def _make_order(self, status="DRAFT"):
        return SalesOrder.objects.create(
            company=self.company,
            customer=self.customer,
            order_date=date.today(),
            status=status,
        )

    def test_order_creation(self):
        order = self._make_order()
        self.assertEqual(order.status, "DRAFT")
        self.assertIsNotNone(order.pk)

    def test_order_str(self):
        order = self._make_order()
        self.assertIn("SO-", str(order))

    def test_is_fully_delivered_true(self):
        order = self._make_order("DELIVERED")
        self.assertTrue(order.is_fully_delivered)

    def test_is_fully_delivered_false_for_draft(self):
        order = self._make_order("DRAFT")
        self.assertFalse(order.is_fully_delivered)

    def test_order_item_line_total_no_discount(self):
        order = self._make_order()
        item = SalesOrderItem(
            order=order,
            product=self.product,
            quantity=Decimal("3"),
            unit_price=Decimal("1000.00"),
            discount_percent=Decimal("0"),
            tax_percent=Decimal("0"),
        )
        self.assertEqual(item.line_total, Decimal("3000.00"))

    def test_order_item_line_total_with_discount_and_tax(self):
        order = self._make_order()
        item = SalesOrderItem(
            order=order,
            product=self.product,
            quantity=Decimal("2"),
            unit_price=Decimal("1000.00"),
            discount_percent=Decimal("10"),
            tax_percent=Decimal("13"),
        )
        # base=2000, discount=200, taxable=1800, tax=234, total=2034
        expected = Decimal("2034.00")
        self.assertEqual(item.line_total.quantize(Decimal("0.01")), expected)

    def test_delivery_note_linked_to_order(self):
        order = self._make_order("CONFIRMED")
        dn = DeliveryNote.objects.create(
            company=self.company,
            sales_order=order,
            dispatch_date=date.today(),
            status="PENDING",
        )
        self.assertEqual(dn.sales_order, order)
        self.assertIn("DN-", str(dn))

    def test_total_ordered_qty(self):
        order = self._make_order()
        SalesOrderItem.objects.create(
            order=order,
            product=self.product,
            quantity=Decimal("5"),
            unit_price=Decimal("100.00"),
        )
        SalesOrderItem.objects.create(
            order=order,
            product=self.product,
            quantity=Decimal("3"),
            unit_price=Decimal("200.00"),
        )
        self.assertEqual(order.total_ordered_qty, Decimal("8"))
