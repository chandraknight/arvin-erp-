"""
IATA BSP file parser and reconciliation engine.

Supported source formats:
  CSV  — columns detected from header row
  XLSX/XLS — first sheet, columns detected from header row

Expected column names (case-insensitive, spaces/underscores interchangeable):
  ticket_number / ticket no / doc number
  passenger_name / pax name / name
  issue_date / date
  airline_code / carrier / validating carrier
  routing / route / sectors
  fare / base fare / fare_amount
  tax / taxes / tax_amount
  fuel_surcharge / ys / yq
  gross / gross_fare / total
  commission / commission_amount
  net / net_fare / net_amount
  bsp_reference / bsp ref / transaction ref / reporting period

The engine:
1. Parses the file row by row
2. Stores each row as IATAReconciliationItem
3. Tries to match each row's ticket_number against existing AirTicket records
4. Flags amount mismatches
5. Optionally auto-imports unmatched rows as new AirTicket records
"""

import csv
import io
import logging
from decimal import Decimal, InvalidOperation
from datetime import date, datetime

from django.utils import timezone

logger = logging.getLogger(__name__)

# ── Column name aliases ────────────────────────────────────────────────────────

_COL_MAP = {
    'ticket_number':  ['ticket_number', 'ticket no', 'ticket_no', 'doc number', 'doc_number', 'document number', 'tkt_no', 'tkt no'],
    'passenger_name': ['passenger_name', 'passenger name', 'pax name', 'pax_name', 'name', 'passenger'],
    'issue_date':     ['issue_date', 'issue date', 'date', 'issued_date', 'issued date', 'transaction date'],
    'airline_code':   ['airline_code', 'airline code', 'carrier', 'validating carrier', 'val carrier', 'airline'],
    'routing':        ['routing', 'route', 'sectors', 'itinerary', 'od'],
    'fare':           ['fare', 'base fare', 'fare_amount', 'base_fare', 'fare amount'],
    'tax':            ['tax', 'taxes', 'tax_amount', 'tax amount'],
    'fuel_surcharge': ['fuel_surcharge', 'fuel surcharge', 'ys', 'yq', 'yq/ys'],
    'gross':          ['gross', 'gross_fare', 'gross fare', 'total', 'gross amount', 'total amount'],
    'commission':     ['commission', 'commission_amount', 'commission amount', 'comm'],
    'net':            ['net', 'net_fare', 'net fare', 'net amount', 'net_amount'],
    'bsp_reference':  ['bsp_reference', 'bsp ref', 'bsp reference', 'transaction ref', 'reporting period', 'period'],
}


def _normalise_header(raw: str) -> str:
    return raw.strip().lower().replace(' ', '_').replace('-', '_')


def _detect_columns(headers: list[str]) -> dict:
    """Return mapping: our_field → column_index (or None if not found)."""
    normalised = [_normalise_header(h) for h in headers]
    result = {}
    for field, aliases in _COL_MAP.items():
        idx = None
        for alias in aliases:
            alias_norm = alias.replace(' ', '_').replace('-', '_')
            if alias_norm in normalised:
                idx = normalised.index(alias_norm)
                break
        result[field] = idx
    return result


def _parse_decimal(val) -> Decimal:
    if val is None or val == '':
        return Decimal('0.00')
    try:
        return Decimal(str(val).replace(',', '').strip()).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError):
        return Decimal('0.00')


def _parse_date(val) -> date | None:
    if val is None or val == '':
        return None
    if isinstance(val, (date, datetime)):
        return val.date() if isinstance(val, datetime) else val
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%m/%d/%Y', '%d %b %Y', '%d-%b-%Y', '%Y%m%d'):
        try:
            return datetime.strptime(str(val).strip(), fmt).date()
        except ValueError:
            continue
    return None


def _get_cell(row: list, idx) -> str:
    if idx is None or idx >= len(row):
        return ''
    val = row[idx]
    return str(val).strip() if val is not None else ''


def _read_rows(source_file_obj) -> tuple[list[str], list[list]]:
    """Return (headers, data_rows) from the uploaded file."""
    path = source_file_obj.file.path
    name = source_file_obj.original_filename.lower()

    if name.endswith('.csv'):
        with open(path, newline='', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            rows = list(reader)
        if not rows:
            return [], []
        return rows[0], rows[1:]

    # Excel
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    rows = [[cell.value for cell in row] for row in ws.iter_rows()]
    wb.close()
    if not rows:
        return [], []
    return [str(h) if h is not None else '' for h in rows[0]], rows[1:]


# ── Main reconciliation function ──────────────────────────────────────────────

def process_iata_source_file(source_file_obj, auto_import=False):
    """
    Parse an IATASourceFile and create IATAReconciliationItem rows.
    Returns a summary dict.

    auto_import=True: unmatched rows are imported as new AirTicket records.
    """
    from .models import AirTicket, IATAReconciliationItem, IATAAirline

    source_file_obj.status = 'PROCESSING'
    source_file_obj.save(update_fields=['status'])

    try:
        headers, data_rows = _read_rows(source_file_obj)
    except Exception as e:
        source_file_obj.status = 'ERROR'
        source_file_obj.error_log = f"File read error: {e}"
        source_file_obj.save(update_fields=['status', 'error_log'])
        return {'error': str(e)}

    if not headers:
        source_file_obj.status = 'ERROR'
        source_file_obj.error_log = 'File appears to be empty or has no header row.'
        source_file_obj.save(update_fields=['status', 'error_log'])
        return {'error': 'Empty file'}

    col = _detect_columns(headers)
    company = source_file_obj.company

    total = matched = unmatched = mismatched = new_imported = 0
    errors = []

    # Delete previous items for this file (re-process)
    IATAReconciliationItem.objects.filter(source_file=source_file_obj).delete()

    for i, row in enumerate(data_rows, start=2):
        raw_ticket = _get_cell(row, col['ticket_number'])
        if not raw_ticket:
            continue  # skip blank rows

        raw_passenger = _get_cell(row, col['passenger_name'])
        raw_date = _parse_date(_get_cell(row, col['issue_date']))
        raw_airline = _get_cell(row, col['airline_code'])[:3].upper() if col['airline_code'] is not None else ''
        raw_routing = _get_cell(row, col['routing'])
        raw_fare = _parse_decimal(_get_cell(row, col['fare']))
        raw_tax = _parse_decimal(_get_cell(row, col['tax']))
        raw_fuel = _parse_decimal(_get_cell(row, col['fuel_surcharge']))
        raw_gross = _parse_decimal(_get_cell(row, col['gross']))
        raw_commission = _parse_decimal(_get_cell(row, col['commission']))
        raw_net = _parse_decimal(_get_cell(row, col['net']))
        raw_bsp = _get_cell(row, col['bsp_reference'])

        # Try to match existing ticket
        try:
            ticket = AirTicket.active_objects.get(company=company, ticket_number=raw_ticket)
            # Check for amount mismatch (gross)
            if raw_gross and abs(ticket.gross_fare - raw_gross) > Decimal('0.01'):
                match_status = 'MISMATCH'
                mismatch_note = (
                    f"Gross fare mismatch: system={ticket.gross_fare}, BSP={raw_gross}. "
                    f"Fare: system={ticket.fare_amount} BSP={raw_fare}. "
                    f"Net: system={ticket.net_fare} BSP={raw_net}."
                )
                mismatched += 1
            else:
                match_status = 'MATCHED'
                mismatch_note = ''
                matched += 1
        except AirTicket.DoesNotExist:
            ticket = None
            if auto_import:
                # Create new AirTicket from BSP data
                airline_obj = None
                if raw_airline:
                    airline_obj = IATAAirline.objects.filter(iata_code=raw_airline).first()
                try:
                    ticket = AirTicket.objects.create(
                        company=company,
                        ticket_number=raw_ticket,
                        passenger_name=raw_passenger or 'UNKNOWN',
                        issue_date=raw_date or timezone.now().date(),
                        airline=airline_obj,
                        validating_carrier=raw_airline,
                        routing=raw_routing,
                        fare_amount=raw_fare,
                        tax_amount=raw_tax,
                        fuel_surcharge=raw_fuel,
                        gross_fare=raw_gross,
                        commission_amount=raw_commission,
                        net_fare=raw_net,
                        bsp_reference=raw_bsp,
                        status='ISSUED',
                        created_by=source_file_obj.uploaded_by,
                    )
                    match_status = 'NEW_IMPORTED'
                    mismatch_note = 'Auto-imported from BSP file.'
                    new_imported += 1
                except Exception as e:
                    errors.append(f"Row {i} import error: {e}")
                    match_status = 'UNMATCHED'
                    mismatch_note = f'Import failed: {e}'
                    unmatched += 1
            else:
                match_status = 'UNMATCHED'
                mismatch_note = 'Ticket not found in system.'
                unmatched += 1

        IATAReconciliationItem.objects.create(
            source_file=source_file_obj,
            air_ticket=ticket,
            raw_ticket_number=raw_ticket,
            raw_passenger_name=raw_passenger,
            raw_issue_date=raw_date,
            raw_airline_code=raw_airline,
            raw_routing=raw_routing,
            raw_fare=raw_fare,
            raw_tax=raw_tax,
            raw_gross=raw_gross,
            raw_commission=raw_commission,
            raw_net=raw_net,
            match_status=match_status,
            mismatch_note=mismatch_note,
        )
        total += 1

    source_file_obj.status = 'PROCESSED'
    source_file_obj.rows_total = total
    source_file_obj.rows_matched = matched
    source_file_obj.rows_unmatched = unmatched + mismatched
    source_file_obj.rows_new = new_imported
    source_file_obj.error_log = '\n'.join(errors)
    source_file_obj.processed_at = timezone.now()
    source_file_obj.save(update_fields=[
        'status', 'rows_total', 'rows_matched', 'rows_unmatched',
        'rows_new', 'error_log', 'processed_at'
    ])

    return {
        'total': total,
        'matched': matched,
        'mismatched': mismatched,
        'unmatched': unmatched,
        'new_imported': new_imported,
        'errors': errors,
    }


def import_iata_airlines_from_csv(file_obj):
    """
    Bulk-import IATA airline codes from a CSV.
    Expected columns: iata_code, name, country, icao_code (optional)
    Returns (created, updated, skipped) counts.
    """
    from .models import IATAAirline
    content = file_obj.read().decode('utf-8-sig')
    reader = csv.DictReader(io.StringIO(content))
    created = updated = skipped = 0
    for row in reader:
        code = row.get('iata_code', row.get('code', '')).strip().upper()
        name = row.get('name', row.get('airline', '')).strip()
        if not code or not name:
            skipped += 1
            continue
        obj, was_created = IATAAirline.objects.update_or_create(
            iata_code=code,
            defaults={
                'name': name,
                'country': row.get('country', '').strip(),
                'icao_code': row.get('icao_code', row.get('icao', '')).strip().upper(),
                'is_active': True,
            }
        )
        if was_created:
            created += 1
        else:
            updated += 1
    return created, updated, skipped


def import_iata_airports_from_csv(file_obj):
    """
    Bulk-import IATA airport codes from a CSV.
    Expected columns: iata_code, name, city, country, country_code, icao_code, latitude, longitude
    Returns (created, updated, skipped) counts.
    """
    from .models import IATAAirport
    content = file_obj.read().decode('utf-8-sig')
    reader = csv.DictReader(io.StringIO(content))
    created = updated = skipped = 0
    for row in reader:
        code = row.get('iata_code', row.get('code', row.get('iata', ''))).strip().upper()
        name = row.get('name', row.get('airport', '')).strip()
        if not code or len(code) != 3:
            skipped += 1
            continue

        def safe_decimal(val):
            try:
                return Decimal(str(val).strip()) if val and str(val).strip() else None
            except InvalidOperation:
                return None

        obj, was_created = IATAAirport.objects.update_or_create(
            iata_code=code,
            defaults={
                'name': name,
                'city': row.get('city', row.get('municipality', '')).strip(),
                'country': row.get('country', row.get('country_name', '')).strip(),
                'country_code': row.get('country_code', row.get('iso_country', '')).strip().upper()[:2],
                'icao_code': row.get('icao_code', row.get('icao', row.get('ident', ''))).strip().upper(),
                'latitude': safe_decimal(row.get('latitude', row.get('lat'))),
                'longitude': safe_decimal(row.get('longitude', row.get('lon'))),
                'is_active': True,
            }
        )
        if was_created:
            created += 1
        else:
            updated += 1
    return created, updated, skipped
