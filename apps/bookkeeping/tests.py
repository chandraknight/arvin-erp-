from datetime import date

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.company.models import Company, FiscalYear
from apps.bookkeeping.models import (
    LedgerAccount, JournalEntry, JournalEntryLine, assert_balanced, reverse_journal,
)


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
            end_date=date(2025, 7, 16),
            start_date_bs="2081-04-01",
            end_date_bs="2082-03-32",
        )
        self.assertEqual(fy.name, "2081/82")

    def test_wrong_start_month_rejected(self):
        with self.assertRaises(ValidationError):
            FiscalYear.objects.create(
                company=self.company,
                start_date=date(2024, 1, 1),
                end_date=date(2025, 1, 1),
                start_date_bs="2081-01-01",
                end_date_bs="2082-03-32",
            )
