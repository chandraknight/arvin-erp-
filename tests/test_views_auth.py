"""
Tests: View-level authentication enforcement.

UAT flows covered:
  - Unauthenticated requests to all major sections redirect to login
  - Authenticated staff user gets 200 on list/dashboard views
"""
import unittest
from django.test import TestCase, Client
from django.urls import reverse

from .base import BaseERPTestCase, _CRED

PROTECTED_URL_NAMES = [
    "billing:billing_dashboard",
    "billing:invoice_list",
    "customers:customer_dashboard",
    "payments:payment_list",
    "payments:expense_list",
    "payments:bank_account_list",
]


class UnauthenticatedRedirectTests(TestCase):
    """Every protected URL must redirect to login when not logged in."""

    def setUp(self):
        self.client = Client()

    def test_protected_views_redirect_to_login(self):
        for name in PROTECTED_URL_NAMES:
            with self.subTest(url=name):
                url = reverse(name)
                resp = self.client.get(url)
                self.assertIn(
                    resp.status_code, [301, 302],
                    msg=f"{name} should redirect unauthenticated users"
                )
                self.assertIn("login", resp["Location"].lower())


class AuthenticatedAccessTests(BaseERPTestCase):
    """Logged-in staff user should reach list/dashboard views (200 or 302-to-self)."""

    def _check_accessible(self, name, **kwargs):
        """Verify the URL is accessible (not bounced to login). Follows redirects."""
        url = reverse(name, kwargs=kwargs) if kwargs else reverse(name)
        resp = self.client.get(url, follow=True)
        final_url = resp.redirect_chain[-1][0] if resp.redirect_chain else url
        self.assertNotIn(
            "/accounts/login/", final_url,
            msg=f"Authenticated user was redirected to login for {name}"
        )
        self.assertIn(
            resp.status_code, [200, 302],
            msg=f"Unexpected status {resp.status_code} for {name}"
        )

    def test_billing_dashboard(self):
        self._check_accessible("billing:billing_dashboard")

    def test_invoice_list(self):
        self._check_accessible("billing:invoice_list")

    def test_customer_dashboard(self):
        self._check_accessible("customers:customer_dashboard")

    def test_payment_list(self):
        self._check_accessible("payments:payment_list")

    def test_expense_list(self):
        self._check_accessible("payments:expense_list")
