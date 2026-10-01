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


class StockRegisterTests(TestCase):
    def setUp(self):
        from apps.products.services.stock_ledger_service import log_movement
        from datetime import date
        self.log = log_movement
        self.company = Company.objects.create(name="Register Co")
        cat = Category.objects.create(company=self.company, name="Cat")
        self.product = Product.objects.create(
            company=self.company, name="Widget", category=cat,
            price=Decimal('100.00'), cost_price=Decimal('10.00'), cost_method='WA',
        )
        self.stock = ProductStock.objects.create(product=self.product, stock=0)
        self.today = date.today()

    def _move(self, txn_type, qty, change, cost='10.00'):
        self.stock.stock += change
        self.stock.save()
        return self.log(self.product, transaction_type=txn_type, quantity=qty,
                        qty_change=change, unit_cost=Decimal(cost))

    def test_register_reconciles_opening_receipts_issues_closing(self):
        from apps.products.services.stock_register_service import build_stock_register
        self._move('ADD', 100, 100)
        self._move('REMOVE', 30, -30)
        rows, totals, lines = build_stock_register(
            self.company, self.today, self.today, product_id=self.product.pk)
        r = rows[0]
        self.assertEqual((r['opening_qty'], r['in_qty'], r['out_qty'], r['closing_qty']), (0, 100, 30, 70))
        self.assertEqual(r['closing_value'], Decimal('700'))
        self.assertEqual([l['bal_qty'] for l in lines], [100, 70])

    def test_transfers_are_not_movements(self):
        from apps.products.services.stock_register_service import build_stock_register
        self._move('ADD', 50, 50)
        self.log(self.product, transaction_type='ADD', stock_type='ECOM', quantity=20, qty_change=0)
        rows, _, lines = build_stock_register(self.company, self.today, self.today, product_id=self.product.pk)
        self.assertEqual(len(lines), 1)
        self.assertEqual(rows[0]['in_qty'], 50)

    def test_opening_balance_excludes_later_movements(self):
        from datetime import timedelta
        from apps.products.services.stock_register_service import build_stock_register
        self._move('ADD', 40, 40)
        rows, _, _ = build_stock_register(
            self.company, self.today + timedelta(days=1), self.today + timedelta(days=2))
        self.assertEqual((rows[0]['opening_qty'], rows[0]['closing_qty']), (40, 40))
