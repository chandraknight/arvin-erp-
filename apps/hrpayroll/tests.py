from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.company.models import Company, FiscalYear
from apps.hrpayroll.models import IncomeTaxSlab
from apps.hrpayroll.services.payroll_tax_service import calculate_income_tax, calculate_ssf


class CalculateIncomeTaxTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Tax Co")
        self.fiscal_year = FiscalYear.objects.create(
            company=self.company, start_date=date(2024, 7, 16), end_date=date(2025, 7, 15),
        )
        IncomeTaxSlab.objects.create(
            company=self.company, fiscal_year=self.fiscal_year, marital_status="SINGLE",
            slab_order=1, upper_limit=Decimal("500000"), rate=Decimal("1.00"),
        )
        IncomeTaxSlab.objects.create(
            company=self.company, fiscal_year=self.fiscal_year, marital_status="SINGLE",
            slab_order=2, upper_limit=None, rate=Decimal("10.00"),
        )

    def test_calculate_income_tax_applies_bracket_rates(self):
        # 500,000 @ 1% + 100,000 @ 10% = 5,000 + 10,000 = 15,000
        tax = calculate_income_tax(Decimal("600000"), "SINGLE", self.company, self.fiscal_year)
        self.assertEqual(tax, Decimal("15000.00"))

    def test_calculate_income_tax_returns_zero_when_slabs_missing(self):
        tax = calculate_income_tax(Decimal("600000"), "MARRIED", self.company, self.fiscal_year)
        self.assertEqual(tax, Decimal("0.00"))


class CalculateSsfTests(TestCase):
    def test_calculate_ssf_returns_employee_and_employer_amounts(self):
        employee_amount, employer_amount = calculate_ssf(Decimal("50000"))
        self.assertEqual((employee_amount, employer_amount), (Decimal("5500.00"), Decimal("10000.00")))
