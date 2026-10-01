from decimal import Decimal

from django.test import TestCase

from apps.company.models import Company
from apps.products.models import Category, Product, ProductStock
from apps.billing.models import Invoice, InvoiceItem
from apps.billing.services.invoice_stock_service import issue_invoice_stock
from apps.bookkeeping.models import JournalEntry


class InvoiceStockIssueTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Inv Stock Co", enable_inventory=True)
        cat = Category.objects.create(company=self.company, name="Cat")
        self.product = Product.objects.create(
            company=self.company, name="Widget", category=cat, price=Decimal('100'),
            cost_price=Decimal('10'), cost_method='WA')
        self.stock = ProductStock.objects.create(product=self.product, stock=100)
        inv = Invoice(company=self.company, total=Decimal('400'), subtotal=Decimal('400'))
        inv._skip_journal = True
        inv.save()
        self.invoice = inv
        InvoiceItem.objects.create(invoice=inv, product=self.product, quantity=4, price=Decimal('100'))

    def test_issue_reduces_stock_posts_cogs_and_is_idempotent(self):
        entry = issue_invoice_stock(self.invoice)
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.stock, 96)
        self.assertEqual(entry.source_type, 'COGS')
        self.assertEqual(entry.lines.get(entry_type='DEBIT').amount, Decimal('40.00'))
        self.assertEqual(self.invoice.items.get().unit_cost, Decimal('10.0000'))

        self.assertIsNone(issue_invoice_stock(self.invoice))
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.stock, 96)
        self.assertEqual(JournalEntry.objects.filter(company=self.company, source_type='COGS').count(), 1)

    def test_untracked_product_is_skipped(self):
        self.stock.delete()
        self.assertIsNone(issue_invoice_stock(self.invoice))
        self.assertFalse(JournalEntry.objects.filter(company=self.company, source_type='COGS').exists())
