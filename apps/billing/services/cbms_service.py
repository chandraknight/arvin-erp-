"""
apps/billing/services/cbms_service.py
======================================
Nepal IRD Central Billing Monitoring System (CBMS) integration.

API endpoints:
  POST https://cbapi.ird.gov.np/api/bill        — submit invoice
  POST https://cbapi.ird.gov.np/api/billreturn  — submit credit note (sales return)

Response codes:
  200 — Success
  100 — API credentials do not match
  101 — Bill already exists (bill) / Bill does not exist (return)
  102 — Exception while saving — check field values
  103 — Unknown exception
  104 — Model invalid
  105 — Bill does not exist (for sales return)
"""

import json
import logging
from datetime import datetime
from decimal import Decimal

import nepali_datetime
import urllib.request
import urllib.error

logger = logging.getLogger('audit')

CBMS_BILL_URL = 'https://cbapi.ird.gov.np/api/bill'
CBMS_RETURN_URL = 'https://cbapi.ird.gov.np/api/billreturn'

CBMS_SUCCESS = '200'


def _fiscal_year_for_cbms(fy_name: str) -> str:
    """
    Convert stored FY name to CBMS format.
    "2082/83"   →  "2082.083"
    "2082-83"   →  "2082.083"
    "2082.083"  →  "2082.083"
    "2073/074"  →  "2073.074"
    """
    if not fy_name:
        return ''
    # Normalize to slash separator
    normalized = fy_name.replace('-', '/').replace('.', '/')
    parts = normalized.split('/')
    if len(parts) == 2:
        start = parts[0].strip()
        end_raw = parts[1].strip()
        # Always zero-pad the end portion to 3 digits
        # 2-digit "83" → "083", 3-digit "083" stays, 4-digit "2083" → last 3 "083"
        if len(end_raw) <= 3:
            end_full = end_raw.zfill(3)
        else:
            end_full = end_raw[-3:]
        return f"{start}.{end_full}"
    return fy_name


def _bs_date_for_cbms(ad_date) -> str:
    """Convert AD date to BS date string in CBMS format: "2082.07.06"."""
    if not ad_date:
        return ''
    try:
        bs = nepali_datetime.date.from_datetime_date(ad_date)
        return f"{bs.year}.{bs.month:02d}.{bs.day:02d}"
    except Exception:
        return str(ad_date)


def _post_to_cbms(url: str, payload: dict) -> tuple[bool, str, str]:
    """
    POST payload as JSON to CBMS. Returns (success, response_code, response_body).
    Uses stdlib urllib — no extra dependencies.
    """
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        url,
        data=data,
        headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode('utf-8').strip()
            code = body.strip('"').strip()
            return code == CBMS_SUCCESS, code, body
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        return False, str(e.code), body
    except Exception as exc:
        return False, 'NETWORK_ERROR', str(exc)


def _safe_payload(payload: dict) -> dict:
    """Return payload copy with password redacted for audit log."""
    safe = dict(payload)
    safe['password'] = '***'
    return safe


def post_bill(invoice) -> 'CBMSSubmission':
    """
    Submit an issued invoice to CBMS.
    Returns the CBMSSubmission audit record.
    Does NOT raise — failures are logged and recorded but do not block the invoice.
    """
    from apps.billing.models import CBMSSubmission

    company = invoice.company
    if not company or not company.enable_ebilling:
        return None

    # Active fiscal year name
    from apps.company.models import FiscalYear
    fy = FiscalYear.objects.filter(company=company, is_active=True).first()
    fy_name = _fiscal_year_for_cbms(fy.name if fy else '')

    taxable = (invoice.subtotal - invoice.discount_amount).quantize(Decimal('0.01'))

    payload = {
        'username': company.cbms_username or '',
        'password': company.cbms_password or '',
        'seller_pan': company.vat_number or '',
        'buyer_pan': (invoice.customer.pan_number or '') if invoice.customer else '',
        'buyer_name': (invoice.customer.name or '') if invoice.customer else '',
        'fiscal_year': fy_name,
        'invoice_number': invoice.invoice_number or '',
        'invoice_date': _bs_date_for_cbms(invoice.transaction_date),
        'total_sales': float(invoice.total),
        'taxable_sales_vat': float(taxable),
        'vat': float(invoice.tax_amount),
        'excisable_amount': 0.0,
        'excise': 0.0,
        'taxable_sales_hst': 0.0,
        'hst': 0.0,
        'amount_for_esf': 0.0,
        'esf': 0.0,
        'export_sales': 0.0,
        'tax_exempted_sales': 0.0,
        'isrealtime': True,
        'datetimeClient': datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
    }

    success, code, body = _post_to_cbms(CBMS_BILL_URL, payload)

    log = CBMSSubmission.objects.create(
        company=company,
        invoice=invoice,
        submission_type='BILL',
        payload=_safe_payload(payload),
        response_code=code,
        response_body=body,
        success=success,
        created_by=invoice.created_by,
    )

    if success:
        logger.info('CBMS_BILL_OK invoice=%s company=%s', invoice.invoice_number, company.name)
    else:
        logger.warning(
            'CBMS_BILL_FAIL invoice=%s company=%s code=%s body=%s',
            invoice.invoice_number, company.name, code, body,
        )

    return log


def post_credit_note(credit_note) -> 'CBMSSubmission':
    """
    Submit a credit note (sales return) to CBMS.
    Returns the CBMSSubmission audit record.
    """
    from apps.billing.models import CBMSSubmission

    company = credit_note.company
    if not company or not company.enable_ebilling:
        return None

    from apps.company.models import FiscalYear
    fy = FiscalYear.objects.filter(company=company, is_active=True).first()
    fy_name = _fiscal_year_for_cbms(fy.name if fy else '')

    original_invoice = credit_note.invoice
    ref_invoice_number = original_invoice.invoice_number if original_invoice else ''
    taxable = credit_note.amount.quantize(Decimal('0.01'))
    # Compute VAT portion if company is VAT-registered
    vat_rate = Decimal(str(company.tax_rate)) / Decimal('100') if company.vat_registered else Decimal('0')
    vat_divisor = Decimal('1') + vat_rate
    if vat_rate > 0:
        # Assume credit_note.amount is VAT-inclusive
        vat = (credit_note.amount - credit_note.amount / vat_divisor).quantize(Decimal('0.01'))
        taxable_base = (credit_note.amount / vat_divisor).quantize(Decimal('0.01'))
    else:
        vat = Decimal('0')
        taxable_base = credit_note.amount

    payload = {
        'username': company.cbms_username or '',
        'password': company.cbms_password or '',
        'seller_pan': company.vat_number or '',
        'buyer_pan': (credit_note.customer.pan_number or '') if credit_note.customer else '',
        'buyer_name': (credit_note.customer.name or '') if credit_note.customer else '',
        'fiscal_year': fy_name,
        'ref_invoice_number': ref_invoice_number,
        'credit_note_number': credit_note.credit_note_number or '',
        'credit_note_date': _bs_date_for_cbms(credit_note.created_at.date()),
        'reason_for_return': credit_note.reason or '',
        'total_sales': float(credit_note.amount),
        'taxable_sales_vat': float(taxable_base),
        'vat': float(vat),
        'excisable_amount': 0.0,
        'excise': 0.0,
        'taxable_sales_hst': 0.0,
        'hst': 0.0,
        'amount_for_esf': 0.0,
        'esf': 0.0,
        'export_sales': 0.0,
        'tax_exempted_sales': 0.0,
        'isrealtime': True,
        'datetimeClient': datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
    }

    success, code, body = _post_to_cbms(CBMS_RETURN_URL, payload)

    log = CBMSSubmission.objects.create(
        company=company,
        credit_note=credit_note,
        submission_type='BILL_RETURN',
        payload=_safe_payload(payload),
        response_code=code,
        response_body=body,
        success=success,
        created_by=credit_note.created_by,
    )

    if success:
        logger.info('CBMS_RETURN_OK cn=%s company=%s', credit_note.credit_note_number, company.name)
    else:
        logger.warning(
            'CBMS_RETURN_FAIL cn=%s company=%s code=%s body=%s',
            credit_note.credit_note_number, company.name, code, body,
        )

    return log
