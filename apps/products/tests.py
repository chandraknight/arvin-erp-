from decimal import Decimal

from django.test import TestCase

from apps.company.models import Company
from apps.products.models import Category, Product, ProductStock, StockLot
from apps.products.services.fifo_service import create_lot, consume_fifo_lots, fifo_stock_value
from apps.products.services.stock_disposal_service import post_stock_disposal


class FifoServiceTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="FIFO Test Co")
        self.category = Category.objects.create(company=self.company, name="Test Category")
        self.product = Product.objects.create(
            company=self.company, name="Test Product", category=self.category,
            price=Decimal('100.00'), cost_method='FIFO',
        )
        ProductStock.objects.create(product=self.product, stock=0)

    def test_consume_deducts_oldest_lot_first(self):
        create_lot(self.product, qty=10, unit_cost=Decimal('5.00'))
        create_lot(self.product, qty=10, unit_cost=Decimal('8.00'))

        consume_fifo_lots(self.product, 5)

        oldest_lot = StockLot.objects.filter(product=self.product).order_by('received_at').first()
        self.assertEqual(oldest_lot.qty_remaining, 5)

    def test_consume_spans_into_second_lot_at_its_own_cost(self):
        create_lot(self.product, qty=10, unit_cost=Decimal('5.00'))
        create_lot(self.product, qty=10, unit_cost=Decimal('8.00'))

        cost = consume_fifo_lots(self.product, 15)

        self.assertEqual(cost, Decimal('10') * Decimal('5.00') + Decimal('5') * Decimal('8.00'))

    def test_consume_shortfall_falls_back_to_cost_price(self):
        # Simulates legacy stock recorded before this product had any lots.
        create_lot(self.product, qty=5, unit_cost=Decimal('5.00'))
        self.product.cost_price = Decimal('12.00')
        self.product.save(update_fields=['cost_price'])

        cost = consume_fifo_lots(self.product, 8)

        self.assertEqual(cost, Decimal('5') * Decimal('5.00') + Decimal('3') * Decimal('12.00'))

    def test_consume_syncs_cost_price_to_new_oldest_lot(self):
        create_lot(self.product, qty=5, unit_cost=Decimal('5.00'))
        create_lot(self.product, qty=5, unit_cost=Decimal('8.00'))

        consume_fifo_lots(self.product, 5)

        self.product.refresh_from_db()
        self.assertEqual(self.product.cost_price, Decimal('8.00'))

    def test_fifo_stock_value_sums_remaining_lots(self):
        create_lot(self.product, qty=10, unit_cost=Decimal('5.00'))
        create_lot(self.product, qty=10, unit_cost=Decimal('8.00'))

        self.assertEqual(fifo_stock_value(self.product), Decimal('10') * Decimal('5.00') + Decimal('10') * Decimal('8.00'))


class StockDisposalFifoTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Disposal FIFO Co")
        self.category = Category.objects.create(company=self.company, name="Test Category")
        self.product = Product.objects.create(
            company=self.company, name="Disposal Product", category=self.category,
            price=Decimal('100.00'), cost_method='FIFO',
        )
        ProductStock.objects.create(product=self.product, stock=10)
        create_lot(self.product, qty=10, unit_cost=Decimal('7.50'))

    def test_disposal_write_off_value_uses_fifo_lot_cost(self):
        stock_txn = post_stock_disposal(self.product, quantity=4, disposal_reason='DAMAGED')

        self.assertEqual(stock_txn.journal_entry.lines.get(entry_type='DEBIT').amount, Decimal('30.00'))
