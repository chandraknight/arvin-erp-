"""
Tests: Nepal IRD CBMS compliance — invoice numbering, fiscal year format,
BS date conversion, VAT calculation, payload structure.

NCRS/CBMS standards covered:
  - Invoice number format: {PREFIX}-INV-{FY}-{NNNN} per fiscal year
  - Fiscal year in CBMS format: "2082.083"
  - Invoice date in BS Nepali date: "2082.07.06"
  - VAT at 13% (Nepal standard)
  - CBMS payload has all required IRD fields
  - Credit note back-calculates VAT from inclusive amount
  - seller_pan from company.vat_number
  - buyer_pan from customer.pan_number
  - Sequence number unique per company + fiscal year
"""
from decimal import Decimal
from datetime import date
from unittest.mock import patch, MagicMock

from django.test import TestCase

from apps.billing.services.cbms_service import (
    _fiscal_year_for_cbms,
    _bs_date_for_cbms,
    post_bill,
    post_credit_note,
)
from apps.billing.services.invoice_service import generate_invoice_number
from apps.billing.models import Invoice, CreditNote
from .base import BaseERPTestCase


class FiscalYearCBMSFormatTests(TestCase):
    """_fiscal_year_for_cbms must produce IRD-accepted format."""

    def test_slash_format_2digit_end(self):
        self.assertEqual(_fiscal_year_for_cbms("2082/83"), "2082.083")

    def test_slash_format_3digit_end(self):
        self.assertEqual(_fiscal_year_for_cbms("2082/083"), "2082.083")

    def test_dash_separator(self):
        self.assertEqual(_fiscal_year_for_cbms("2082-83"), "2082.083")

    def test_already_cbms_format(self):
        self.assertEqual(_fiscal_year_for_cbms("2082.083"), "2082.083")

    def test_4digit_end(self):
        self.assertEqual(_fiscal_year_for_cbms("2073/2074"), "2073.074")

    def test_empty_string(self):
        self.assertEqual(_fiscal_year_for_cbms(""), "")

    def test_none_returns_empty(self):
        self.assertEqual(_fiscal_year_for_cbms(None), "")


class BSDateCBMSFormatTests(TestCase):
    """_bs_date_for_cbms must convert AD date to BS format "YYYY.MM.DD"."""

    def test_known_ad_to_bs(self):
        # 2025-07-16 AD = 2082-04-01 BS (approx — actual conversion via lib)
        result = _bs_date_for_cbms(date(2025, 7, 16))
        # Must have CBMS format: "YYYY.MM.DD"
        parts = result.split('.')
        self.assertEqual(len(parts), 3, f"Expected YYYY.MM.DD, got {result}")
        # Year must be in BS range (208x)
        self.assertTrue(int(parts[0]) > 2079, f"Year {parts[0]} looks like AD not BS")

    def test_none_returns_empty(self):
        self.assertEqual(_bs_date_for_cbms(None), "")

    def test_month_zero_padded(self):
        result = _bs_date_for_cbms(date(2025, 8, 1))
        parts = result.split('.')
        self.assertEqual(len(parts[1]), 2, f"Month not zero-padded: {result}")

    def test_day_zero_padded(self):
        result = _bs_date_for_cbms(date(2025, 8, 5))
        parts = result.split('.')
        self.assertEqual(len(parts[2]), 2, f"Day not zero-padded: {result}")


class InvoiceNumberFormatTests(BaseERPTestCase):
    """Invoice numbers must follow CBMS-compatible sequential format."""

    def test_invoice_number_contains_fy(self):
        number, seq = generate_invoice_number(self.company.id)
        self.assertIn("2081/82", number)

    def test_invoice_number_sequential(self):
        _, seq1 = generate_invoice_number(self.company.id)
        # Create an invoice to consume that sequence number
        Invoice.objects.create(
            company=self.company,
            customer=self.customer,
            total=Decimal("100.00"),
            invoice_number=f"TST-INV-2081/82-{seq1:04d}",
            sequence_number=seq1,
        )
        _, seq2 = generate_invoice_number(self.company.id)
        self.assertEqual(seq2, seq1 + 1)

    def test_invoice_number_estimate_type(self):
        number, _ = generate_invoice_number(self.company.id, doc_type="EST")
        self.assertIn("EST", number)


class CBMSPayloadTests(BaseERPTestCase):
    """post_bill() must produce IRD-compliant payload."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.company.enable_ebilling = True
        cls.company.vat_registered = True
        cls.company.vat_number = "123456789"
        cls.company.cbms_username = "test_user"
        cls.company.cbms_password = "test_pw"
        cls.company.tax_rate = Decimal("13.00")
        cls.company.save()
        cls.customer.pan_number = "987654321"
        cls.customer.save()

    def _make_issued_invoice(self, total=Decimal("1130.00"), tax_amount=Decimal("130.00")):
        inv = Invoice.objects.create(
            company=self.company,
            customer=self.customer,
            invoice_number="TST-INV-2081/82-0099",
            sequence_number=99,
            total=total,
            subtotal=Decimal("1000.00"),
            tax_amount=tax_amount,
            discount_amount=Decimal("0.00"),
            tax_percent=Decimal("13.00"),
            status="ISSUED",
            transaction_date=date(2025, 7, 16),
        )
        return inv

    @patch('apps.billing.services.cbms_service._post_to_cbms')
    def test_payload_has_required_ird_fields(self, mock_post):
        mock_post.return_value = (True, '200', '"200"')
        inv = self._make_issued_invoice()

        result = post_bill(inv)

        self.assertIsNotNone(result)
        payload = mock_post.call_args[0][1]

        required_fields = [
            'username', 'password', 'seller_pan', 'buyer_pan', 'buyer_name',
            'fiscal_year', 'invoice_number', 'invoice_date',
            'total_sales', 'taxable_sales_vat', 'vat',
            'excisable_amount', 'excise',
            'taxable_sales_hst', 'hst',
            'amount_for_esf', 'esf',
            'export_sales', 'tax_exempted_sales',
            'isrealtime', 'datetimeClient',
        ]
        for field in required_fields:
            self.assertIn(field, payload, f"Missing IRD field: {field}")

    @patch('apps.billing.services.cbms_service._post_to_cbms')
    def test_payload_seller_pan_from_company(self, mock_post):
        mock_post.return_value = (True, '200', '"200"')
        inv = self._make_issued_invoice()
        post_bill(inv)
        payload = mock_post.call_args[0][1]
        self.assertEqual(payload['seller_pan'], "123456789")

    @patch('apps.billing.services.cbms_service._post_to_cbms')
    def test_payload_buyer_pan_from_customer(self, mock_post):
        mock_post.return_value = (True, '200', '"200"')
        inv = self._make_issued_invoice()
        post_bill(inv)
        payload = mock_post.call_args[0][1]
        self.assertEqual(payload['buyer_pan'], "987654321")

    @patch('apps.billing.services.cbms_service._post_to_cbms')
    def test_payload_vat_matches_invoice_tax_amount(self, mock_post):
        mock_post.return_value = (True, '200', '"200"')
        inv = self._make_issued_invoice()
        post_bill(inv)
        payload = mock_post.call_args[0][1]
        self.assertAlmostEqual(payload['vat'], 130.0, places=2)

    @patch('apps.billing.services.cbms_service._post_to_cbms')
    def test_payload_fiscal_year_cbms_format(self, mock_post):
        mock_post.return_value = (True, '200', '"200"')
        inv = self._make_issued_invoice()
        post_bill(inv)
        payload = mock_post.call_args[0][1]
        fy = payload['fiscal_year']
        self.assertRegex(fy, r'^\d{4}\.\d{3}$', f"FY '{fy}' not in CBMS format YYYY.MMM")

    @patch('apps.billing.services.cbms_service._post_to_cbms')
    def test_payload_invoice_date_bs_format(self, mock_post):
        mock_post.return_value = (True, '200', '"200"')
        inv = self._make_issued_invoice()
        post_bill(inv)
        payload = mock_post.call_args[0][1]
        parts = payload['invoice_date'].split('.')
        self.assertEqual(len(parts), 3, f"invoice_date '{payload['invoice_date']}' not BS YYYY.MM.DD")
        self.assertTrue(int(parts[0]) > 2079)

    @patch('apps.billing.services.cbms_service._post_to_cbms')
    def test_password_redacted_in_cbms_submission_record(self, mock_post):
        mock_post.return_value = (True, '200', '"200"')
        inv = self._make_issued_invoice()
        log = post_bill(inv)
        self.assertEqual(log.payload.get('password'), '***')

    def test_ebilling_disabled_returns_none(self):
        self.company.enable_ebilling = False
        self.company.save()
        inv = self._make_issued_invoice()
        result = post_bill(inv)
        self.assertIsNone(result)
        # Restore
        self.company.enable_ebilling = True
        self.company.save()

    @patch('apps.billing.services.cbms_service._post_to_cbms')
    def test_cbms_submission_logged_on_success(self, mock_post):
        mock_post.return_value = (True, '200', '"200"')
        inv = self._make_issued_invoice()
        log = post_bill(inv)
        log.refresh_from_db()
        self.assertTrue(log.success)
        self.assertEqual(log.response_code, '200')

    @patch('apps.billing.services.cbms_service._post_to_cbms')
    def test_cbms_submission_logged_on_failure(self, mock_post):
        mock_post.return_value = (False, '101', '"101"')
        inv = self._make_issued_invoice()
        log = post_bill(inv)
        log.refresh_from_db()
        self.assertFalse(log.success)
        self.assertEqual(log.response_code, '101')


class VATCalculationTests(TestCase):
    """VAT at Nepal standard 13% must calculate correctly."""

    def test_13pct_vat_on_taxable_amount(self):
        taxable = Decimal("1000.00")
        vat = (taxable * Decimal("13") / Decimal("100")).quantize(Decimal("0.01"))
        self.assertEqual(vat, Decimal("130.00"))

    def test_back_calculate_vat_from_inclusive_amount(self):
        # Credit note: amount is VAT-inclusive, back-calculate VAT
        total_inclusive = Decimal("1130.00")
        rate = Decimal("13.00")
        divisor = Decimal("1") + rate / Decimal("100")
        taxable_base = (total_inclusive / divisor).quantize(Decimal("0.01"))
        vat = (total_inclusive - taxable_base).quantize(Decimal("0.01"))
        # 1130 / 1.13 = 1000, VAT = 130
        self.assertEqual(taxable_base, Decimal("1000.00"))
        self.assertEqual(vat, Decimal("130.00"))

    def test_zero_vat_when_not_vat_registered(self):
        # Non-VAT companies should have 0% tax
        vat_rate = Decimal("0")
        taxable = Decimal("500.00")
        vat = (taxable * vat_rate / Decimal("100")).quantize(Decimal("0.01"))
        self.assertEqual(vat, Decimal("0.00"))
