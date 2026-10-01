from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.company.models import Company, FiscalYear
from apps.bookkeeping.models import (
    LedgerAccount, JournalEntry, JournalEntryLine, TDSRate, assert_balanced, reverse_journal,
)
from apps.bookkeeping.tds_service import calculate_tds


class DoubleEntryBalanceTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Test Co")
        self.cash, _ = LedgerAccount.objects.get_or_create(
            company=self.company, name="Cash", defaults={"account_type": "ASSET"},
        )
        self.revenue, _ = LedgerAccount.objects.get_or_create(
            company=self.company, name="Sales Revenue", defaults={"account_type": "REVENUE"},
        )

    def test_balanced_entry_passes(self):
        entry = JournalEntry.objects.create(company=self.company, description="Sale")
        JournalEntryLine.objects.bulk_create([
            JournalEntryLine(journal_entry=entry, account=self.cash, entry_type="DEBIT", amount=100),
            JournalEntryLine(journal_entry=entry, account=self.revenue, entry_type="CREDIT", amount=100),
        ])
        assert_balanced(entry)  # must not raise

    def test_unbalanced_entry_is_rejected(self):
        # A DB-level trigger (Postgres) also enforces this at commit; assert_balanced
        # is the ORM-level backstop used on non-Postgres backends and for early feedback.
        entry = JournalEntry.objects.create(company=self.company, description="Bad sale")
        JournalEntryLine.objects.bulk_create([
            JournalEntryLine(journal_entry=entry, account=self.cash, entry_type="DEBIT", amount=100),
            JournalEntryLine(journal_entry=entry, account=self.revenue, entry_type="CREDIT", amount=90),
        ])
        self.assertFalse(entry.is_balanced)
        with self.assertRaises(ValueError):
            assert_balanced(entry)
        # Clean up so the deferred DB-level balance trigger doesn't fire at
        # transaction teardown for this intentionally-unbalanced fixture.
        entry.lines.all().delete()
        entry.delete()

    def test_normal_balance_auto_derived(self):
        self.assertEqual(self.cash.normal_balance, "DEBIT")
        self.assertEqual(self.revenue.normal_balance, "CREDIT")

    def test_reversal_is_balanced(self):
        entry = JournalEntry.objects.create(company=self.company, description="Sale")
        JournalEntryLine.objects.bulk_create([
            JournalEntryLine(journal_entry=entry, account=self.cash, entry_type="DEBIT", amount=50),
            JournalEntryLine(journal_entry=entry, account=self.revenue, entry_type="CREDIT", amount=50),
        ])
        reversal = reverse_journal(entry, reason="test reversal")
        assert_balanced(reversal)


class FiscalYearSpanTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="FY Co")

    def test_valid_shrawan_to_ashad_span_accepted(self):
        fy = FiscalYear.objects.create(
            company=self.company,
            start_date=date(2024, 7, 16),
            end_date=date(2025, 7, 15),
            start_date_bs="2081-04-01",
            end_date_bs="2082-03-31",
        )
        self.assertEqual(fy.name, "2081/82")

    def test_wrong_start_month_rejected(self):
        with self.assertRaises(ValueError):
            FiscalYear.objects.create(
                company=self.company,
                start_date=date(2024, 1, 1),
                end_date=date(2025, 1, 1),
                start_date_bs="2081-01-01",
                end_date_bs="2082-03-31",
            )


class CalculateTdsTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="TDS Co")
        from apps.vendors.models import Vendor
        from apps.billing.models import VendorBill
        self.vendor = Vendor.objects.create(company=self.company, name="Test Vendor")
        TDSRate.objects.create(
            company=self.company, category="RENT", rate=Decimal("10.00"),
            effective_from=date(2024, 1, 1),
        )
        self.bill = VendorBill.objects.create(
            vendor=self.vendor, bill_number="TDS-BILL-1", bill_date=date(2024, 6, 1),
            total_amount=Decimal("1000.00"), tds_category="RENT",
        )

    def test_calculate_tds_applies_active_rate(self):
        self.assertEqual(calculate_tds(self.bill), Decimal("100.00"))

    def test_calculate_tds_returns_zero_without_category(self):
        self.bill.tds_category = None
        self.assertEqual(calculate_tds(self.bill), Decimal("0.00"))


class SingleDoorPostingTests(TestCase):
    def setUp(self):
        from apps.bookkeeping.models import get_or_create_system_account
        self.company = Company.objects.create(name="Door Co")
        self.cash = get_or_create_system_account(self.company, "Cash", "ASSET", code="1000")
        self.sales = get_or_create_system_account(self.company, "Sales Revenue", "REVENUE", code="4000")

    def test_post_journal_entry_rejects_unbalanced(self):
        from django.core.exceptions import ValidationError
        from apps.bookkeeping.models import post_journal_entry
        with self.assertRaises(ValidationError):
            post_journal_entry(
                self.company, date(2026, 1, 1), "bad",
                [{'account': self.cash, 'entry_type': 'DEBIT', 'amount': Decimal('100')},
                 {'account': self.sales, 'entry_type': 'CREDIT', 'amount': Decimal('90')}],
            )
        self.assertFalse(JournalEntry.objects.filter(description="bad").exists())

    def test_post_journal_entry_sets_source_and_balances(self):
        from apps.bookkeeping.models import post_journal_entry
        entry = post_journal_entry(
            self.company, None, "ok",
            [{'account': self.cash, 'entry_type': 'DEBIT', 'amount': Decimal('10.005')},
             {'account': self.sales, 'entry_type': 'CREDIT', 'amount': Decimal('10.005')}],
            source_type='COGS',
        )
        self.assertEqual(entry.source_type, 'COGS')
        self.assertTrue(entry.is_balanced)

    def test_cogs_posts_dr_cogs_cr_inventory(self):
        from apps.products.services.cogs_service import post_cogs_journal
        entry = post_cogs_journal(self.company, "COGS test", Decimal('250.00'))
        by_side = {(l.account.name, l.entry_type): l.amount for l in entry.lines.all()}
        self.assertEqual(by_side[("Cost of Goods Sold", "DEBIT")], Decimal('250.00'))
        self.assertEqual(by_side[("Inventory", "CREDIT")], Decimal('250.00'))
        self.assertEqual(entry.source_type, 'COGS')

    def test_inventory_ledger_balance_and_posted_cogs(self):
        from apps.bookkeeping.models import post_journal_entry, get_inventory_account, get_cogs_account
        from apps.products.services.cogs_service import post_cogs_journal
        from apps.reports.views import get_inventory_ledger_balance, get_posted_cogs
        inv = get_inventory_account(self.company)
        post_journal_entry(self.company, None, "purchase", [
            {'account': inv, 'entry_type': 'DEBIT', 'amount': Decimal('1000')},
            {'account': self.cash, 'entry_type': 'CREDIT', 'amount': Decimal('1000')}])
        post_cogs_journal(self.company, "sale", Decimal('300'))
        self.assertEqual(get_inventory_ledger_balance(self.company), Decimal('700.00'))
        self.assertEqual(get_posted_cogs(self.company), Decimal('300.00'))


class AccountCodeCollisionTests(TestCase):
    def test_service_accounts_do_not_reuse_default_account_codes(self):
        """Salary / depreciation / disposal / COGS accounts must not resolve to a default account by code."""
        from apps.bookkeeping.models import get_or_create_system_account, get_cogs_account
        from apps.company.services.company_services import setup_default_ledger_accounts
        company = Company.objects.create(name="Code Co")
        setup_default_ledger_accounts(company)
        salary = get_or_create_system_account(company, "Salary Expense", "EXPENSE", code="5400")
        dep = get_or_create_system_account(company, "Depreciation Expense", "EXPENSE", code="5920")
        loss = get_or_create_system_account(company, "Loss on Disposal of Asset", "EXPENSE", code="5960")
        cogs = get_cogs_account(company)
        names = {a.name for a in (salary, dep, loss, cogs)}
        self.assertEqual(names, {"Salary Expense", "Depreciation Expense", "Loss on Disposal of Asset", "Cost of Goods Sold"})
        self.assertEqual(LedgerAccount.objects.get(company=company, code="5300").name, "Staff Meal Expense")
        self.assertEqual(LedgerAccount.objects.get(company=company, code="5200").name, "Purchase Returns")
