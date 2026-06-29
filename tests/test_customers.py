"""
Tests: Customer creation flow, ledger account auto-creation, opening balance.

UAT flows covered:
  - Customer created with auto-assigned LedgerAccount
  - Customer without company raises ValueError
  - Opening balance created for active fiscal year
  - str() returns customer name
"""
from decimal import Decimal

from apps.bookkeeping.models import LedgerAccount, LedgerOpeningBalance
from apps.customers.models import Customer
from .base import BaseERPTestCase


class CustomerCreationTests(BaseERPTestCase):

    def test_customer_has_ledger_account(self):
        self.assertIsNotNone(self.customer.related_ledger_account)
        self.assertEqual(
            self.customer.related_ledger_account.account_type, "ASSET"
        )

    def test_customer_ledger_account_name_contains_customer_name(self):
        self.assertIn("John Doe", self.customer.related_ledger_account.name)

    def test_customer_opening_balance_created(self):
        balance = LedgerOpeningBalance.objects.filter(
            account=self.customer.related_ledger_account,
            fiscal_year=self.fiscal_year,
        ).first()
        self.assertIsNotNone(balance)
        self.assertEqual(balance.amount, 0)
        self.assertEqual(balance.opening_type, "DEBIT")

    def test_customer_str(self):
        self.assertEqual(str(self.customer), "John Doe")

    def test_customer_without_company_raises(self):
        with self.assertRaises(ValueError):
            Customer.objects.create(
                company=None,
                name="No Company Customer",
            )

    def test_customer_update_opening_balance(self):
        self.customer.update_opening_balance(amount=Decimal("10000.00"), opening_type="DEBIT")
        balance = LedgerOpeningBalance.objects.get(
            account=self.customer.related_ledger_account,
            fiscal_year=self.fiscal_year,
        )
        self.assertEqual(balance.amount, Decimal("10000.00"))

    def test_duplicate_email_raises(self):
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            Customer.objects.create(
                company=self.company,
                name="Duplicate Email",
                email="john@testcorp.com",  # same as cls.customer
            )
