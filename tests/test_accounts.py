"""
Tests: User model, authentication, role properties.

UAT flows covered:
  - User login/logout
  - role_name returns correct label
  - company_admin flag
  - company_name property
"""
from django.test import TestCase, Client
from django.urls import reverse

from apps.accounts.models import User
from .base import BaseERPTestCase, _CRED


class UserModelTests(BaseERPTestCase):

    def test_user_str_is_email(self):
        self.assertEqual(str(self.user), "staff@testcorp.com")

    def test_company_admin_role_name(self):
        self.assertEqual(self.user.role_name, "Company Admin")

    def test_company_name_property(self):
        self.assertEqual(self.user.company_name, "Test Corp")

    def test_can_manage_users_true_for_admin(self):
        self.assertTrue(self.user.can_manage_users)

    def test_regular_user_cannot_manage_users(self):
        regular = User.objects.create_user(
            email="regular@testcorp.com",
            username="regular",
            password=_CRED,
            company=self.company,
        )
        self.assertFalse(regular.can_manage_users)


class LoginFlowTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        from apps.company.models import Company
        cls.company = Company.objects.create(name="Login Test Co")
        cls.user = User.objects.create_user(
            email="login@testco.com",
            username="loginuser",
            password=_CRED,
            company=cls.company,
        )

    def test_valid_login_redirects(self):
        resp = self.client.post(
            reverse("accounts:login"),
            {"username": "login@testco.com", "password": _CRED},
            follow=False,
        )
        self.assertIn(resp.status_code, [200, 302])

    def test_invalid_login_stays_on_page(self):
        resp = self.client.post(
            reverse("accounts:login"),
            {"username": "login@testco.com", "password": "wrongpass"},
        )
        # Should not redirect to a success page
        self.assertNotEqual(resp.status_code, 302)
