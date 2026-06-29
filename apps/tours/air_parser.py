"""
IATA BSP AIR (Agency Invoice Report) file parser.

Supported input formats:
  1. IATA fixed-width .air text file  — the canonical BSP remittance format
  2. CSV summary export               — flexible column mapping
  3. Excel (.xlsx/.xls)              — first sheet, flexible column mapping

The parser extracts billing-period summary figures:
  total_sales, total_refunds, total_commission, total_taxes, net_amount_due,
  billing_reference, period_from, period_to.

Returns a ParsedAIR named-tuple; None values mean the field was not found.
"""

import csv
import io
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ParsedAIR:
    billing_reference: str = ''
    period_from: Optional[date] = None
    period_to: Optional[date] = None
    total_sales: Decimal = Decimal('0.00')
    total_refunds: Decimal = Decimal('0.00')
    total_commission: Decimal = Decimal('0.00')
    total_taxes: Decimal = Decimal('0.00')
    net_amount_due: Decimal = Decimal('0.00')
    raw_text: str = ''
    errors: list = field(default_factory=list)


# ── helpers ───────────────────────────────────────────────────────────────────

def _dec(val) -> Decimal:
    if val is None or str(val).strip() == '':
        return Decimal('0.00')
    try:
        clean = str(val).replace(',', '').replace('(', '-').replace(')', '').strip()
        return Decimal(clean).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError):
        return Decimal('0.00')


def _parse_date(val) -> Optional[date]:
    if not val:
        return None
    if isinstance(val, date):
        return val
    if isinstance(val, datetime):
        return val.date()
    s = str(val).strip()
    for fmt in ('%d%b%Y', '%d-%b-%Y', '%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%d-%m-%Y', '%Y%m%d', '%d %b %Y'):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _norm_key(s: str) -> str:
    return re.sub(r'[\s_\-/]+', '_', s.strip().lower())


# ── Fixed-width IATA AIR format parser ───────────────────────────────────────
#
# IATA AIR files are ASCII text.  Key lines to look for (labels vary by BSP):
#   BILLING PERIOD  : 01JAN2024 - 31JAN2024
#   BILLING REF     : 2024010001
#   TOTAL SALES     :      1234567.89
#   TOTAL REFUNDS   :         1000.00
#   COMMISSION      :        61728.39
#   TAXES           :        98765.43
#   NET AMOUNT DUE  :      1172573.89

_LABEL_PATTERNS = {
    'period':       re.compile(r'(?:billing\s*period|period|report\s*period)[:\s]+(.+)', re.I),
    'reference':    re.compile(r'(?:billing\s*ref(?:erence)?|remittance\s*(?:id|ref|no)|invoice\s*no?|ref(?:erence)?)[:\s]+([^\s]+)', re.I),
    'total_sales':  re.compile(r'(?:total\s*sales?|gross\s*sales?|total\s*transactions?)[:\s]+([\d,.()\-]+)', re.I),
    'total_refunds':re.compile(r'(?:total\s*refunds?|refunds?\s*(?:and\s*voids?)?|voids?)[:\s]+([\d,.()\-]+)', re.I),
    'commission':   re.compile(r'(?:total\s*)?commission(?:\s*earned)?[:\s]+([\d,.()\-]+)', re.I),
    'taxes':        re.compile(r'(?:total\s*)?tax(?:es)?[:\s]+([\d,.()\-]+)', re.I),
    'net_due':      re.compile(r'(?:net\s*(?:amount\s*)?(?:due|payable|remittance)|amount\s*(?:due|payable))[:\s]+([\d,.()\-]+)', re.I),
}

_PERIOD_RANGE = re.compile(
    r'(\d{1,2}[A-Za-z]{3}\d{4}|\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4})'
    r'\s*[-–to]+\s*'
    r'(\d{1,2}[A-Za-z]{3}\d{4}|\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4})',
    re.I,
)


def _parse_fixed_text(text: str) -> ParsedAIR:
    result = ParsedAIR(raw_text=text[:2000])
    for line in text.splitlines():
        for key, pat in _LABEL_PATTERNS.items():
            m = pat.search(line)
            if not m:
                continue
            val = m.group(1).strip()
            if key == 'period':
                pm = _PERIOD_RANGE.search(val)
                if pm:
                    result.period_from = _parse_date(pm.group(1))
                    result.period_to = _parse_date(pm.group(2))
            elif key == 'reference':
                if not result.billing_reference:
                    result.billing_reference = val
            elif key == 'total_sales':
                result.total_sales = _dec(val)
            elif key == 'total_refunds':
                result.total_refunds = _dec(val)
            elif key == 'commission':
                result.total_commission = _dec(val)
            elif key == 'taxes':
                result.total_taxes = _dec(val)
            elif key == 'net_due':
                result.net_amount_due = _dec(val)
    return result


# ── CSV / Excel tabular parser ────────────────────────────────────────────────
#
# Some BSPs export AIR data as a summary row CSV/Excel.
# Column aliases we accept:

_CSV_MAP = {
    'billing_reference': ['billing_ref', 'billing_reference', 'remittance_id', 'invoice_no', 'ref', 'reference'],
    'period_from':       ['period_from', 'from', 'start_date', 'period_start', 'billing_from'],
    'period_to':         ['period_to', 'to', 'end_date', 'period_end', 'billing_to'],
    'total_sales':       ['total_sales', 'gross_sales', 'sales', 'total_transactions', 'gross'],
    'total_refunds':     ['total_refunds', 'refunds', 'voids', 'refunds_voids'],
    'total_commission':  ['commission', 'total_commission', 'commission_earned', 'comm'],
    'total_taxes':       ['taxes', 'total_taxes', 'tax'],
    'net_amount_due':    ['net_amount_due', 'net_due', 'net_payable', 'amount_due', 'net'],
}


def _detect_csv_cols(headers: list) -> dict:
    norm = {_norm_key(h): i for i, h in enumerate(headers)}
    mapping = {}
    for field_name, aliases in _CSV_MAP.items():
        for alias in aliases:
            key = _norm_key(alias)
            if key in norm:
                mapping[field_name] = norm[key]
                break
    return mapping


def _parse_tabular(headers: list, rows: list) -> ParsedAIR:
    result = ParsedAIR()
    col = _detect_csv_cols(headers)
    if not rows:
        result.errors.append('File has no data rows.')
        return result

    def cell(row, field_name):
        idx = col.get(field_name)
        if idx is None or idx >= len(row):
            return None
        v = row[idx]
        return str(v).strip() if v is not None else None

    # Aggregate across all rows (supports single-row summary or multi-row detail)
    for row in rows:
        result.total_sales      += _dec(cell(row, 'total_sales'))
        result.total_refunds    += _dec(cell(row, 'total_refunds'))
        result.total_commission += _dec(cell(row, 'total_commission'))
        result.total_taxes      += _dec(cell(row, 'total_taxes'))
        result.net_amount_due   += _dec(cell(row, 'net_amount_due'))

        if not result.billing_reference:
            result.billing_reference = cell(row, 'billing_reference') or ''
        if not result.period_from:
            result.period_from = _parse_date(cell(row, 'period_from'))
        if not result.period_to:
            result.period_to = _parse_date(cell(row, 'period_to'))

    return result


# ── Main entry point ──────────────────────────────────────────────────────────

def parse_air_file(file_path: str, original_filename: str) -> ParsedAIR:
    """
    Parse an uploaded AIR file and return a ParsedAIR with extracted figures.
    Tries fixed-text parsing first; falls back to tabular (CSV/Excel).
    """
    name_lower = original_filename.lower()

    if name_lower.endswith('.csv'):
        try:
            with open(file_path, newline='', encoding='utf-8-sig') as f:
                content = f.read()
            reader = csv.reader(io.StringIO(content))
            all_rows = list(reader)
            if not all_rows:
                r = ParsedAIR()
                r.errors.append('CSV file is empty.')
                return r
            return _parse_tabular(all_rows[0], all_rows[1:])
        except Exception as e:
            logger.exception('AIR CSV parse error')
            r = ParsedAIR()
            r.errors.append(f'CSV read error: {e}')
            return r

    if name_lower.endswith(('.xlsx', '.xls')):
        try:
            import openpyxl
            wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
            ws = wb.active
            all_rows = [[cell.value for cell in row] for row in ws.iter_rows()]
            wb.close()
            if not all_rows:
                r = ParsedAIR()
                r.errors.append('Excel file is empty.')
                return r
            headers = [str(h) if h is not None else '' for h in all_rows[0]]
            return _parse_tabular(headers, all_rows[1:])
        except Exception as e:
            logger.exception('AIR Excel parse error')
            r = ParsedAIR()
            r.errors.append(f'Excel read error: {e}')
            return r

    # Fixed-width text (default for .air, .txt, unknown extensions)
    try:
        with open(file_path, encoding='utf-8-sig', errors='replace') as f:
            text = f.read()
        result = _parse_fixed_text(text)
        # If fixed-text found nothing useful, try treating as CSV
        if result.total_sales == Decimal('0.00') and result.net_amount_due == Decimal('0.00'):
            reader = csv.reader(io.StringIO(text))
            all_rows = list(reader)
            if len(all_rows) > 1:
                alt = _parse_tabular(all_rows[0], all_rows[1:])
                if alt.total_sales > 0 or alt.net_amount_due > 0:
                    return alt
        return result
    except Exception as e:
        logger.exception('AIR text parse error')
        r = ParsedAIR()
        r.errors.append(f'File read error: {e}')
        return r
