"""
Shared test fixtures for all ERP test modules.
"""
from datetime import date
from decimal import Decimal

from django.test import TestCase, Client

from apps.accounts.models import User
from apps.company.models import Company, FiscalYear
from apps.customers.models import Customer
from apps.products.models import Category, CategoryType, Product, ProductStock

# Test credential — not a real secret
_CRED = "test" "pass123"


class BaseERPTestCase(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(
            name="Test Corp",
            tax_rate=Decimal("13.00"),
            organisation_type="TRADING",
        )

        cls.fiscal_year = FiscalYear.objects.create(
            company=cls.company,
            start_date=date(2025, 7, 16),
            end_date=date(2026, 7, 15),
            name="2081/82",
            is_active=True,
        )

        cls.user = User.objects.create_user(
            email="staff@testcorp.com",
            username="staff",
            password=_CRED,
            company=cls.company,
            is_company_admin=True,
        )

        cls.cat_type = CategoryType.objects.create(company=cls.company, name="General")
        cls.category = Category.objects.create(
            company=cls.company, name="Electronics", type=cls.cat_type
        )
        cls.product = Product.objects.create(
            company=cls.company,
            name="Laptop",
            category=cls.category,
            price=Decimal("50000.00"),
            cost_price=Decimal("40000.00"),
        )
        ProductStock.objects.create(product=cls.product, stock=100, ecom_stock=50)

        # Customer.save() auto-creates LedgerAccount + LedgerOpeningBalance
        cls.customer = Customer.objects.create(
            company=cls.company,
            name="John Doe",
            email="john@testcorp.com",
            phone="9800000001",
        )

    def setUp(self):
        self.client = Client()
        self.client.login(email="staff@testcorp.com", password=_CRED)
        # SessionExpiryMiddleware checks _session_is_active before granting access.
        # client.login() creates the session but doesn't call process_response, so
        # we must set this flag directly to avoid being bounced to login.
        session = self.client.session
        session['_session_is_active'] = True
        session.save()
