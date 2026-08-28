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
