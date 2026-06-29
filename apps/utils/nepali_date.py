"""
apps/utils/nepali_date.py
=========================
Utilities for converting between Bikram Sambat (BS) and Gregorian (AD) dates.

All public functions accept and return standard Python datetime.date objects
or YYYY-MM-DD strings. They never raise — on any conversion failure they fall
back gracefully so views don't crash on bad input.

Usage in views
--------------
    from apps.utils.nepali_date import bs_str_to_ad, ad_date_to_bs_str, parse_bs_date

    # Convert a BS string from a form/query-param to an AD date for DB queries
    ad_date = bs_str_to_ad(request.GET.get('start_date'))   # None on failure

    # Convert an AD date to a BS string for display
    bs_str = ad_date_to_bs_str(invoice.transaction_date)    # '' on failure

Usage in forms — fiscal year validation
-----------------------------------------
    Add FiscalYearDateMixin to any ModelForm that has date fields.
    The mixin reads the active fiscal year from request.session and
    validates every NepaliDateField against it automatically.

        from apps.utils.nepali_date import FiscalYearDateMixin, NepaliDateField, NepaliDateWidget

        class MyForm(FiscalYearDateMixin, forms.ModelForm):
            date = NepaliDateField(widget=NepaliDateWidget(), required=True)

            def __init__(self, *args, **kwargs):
                self.request = kwargs.pop('request', None)
                super().__init__(*args, **kwargs)
                self.inject_fiscal_year(self.request)   # call after super().__init__
"""

from __future__ import annotations

import logging
from datetime import date as _date
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import nepali_datetime as _npdt
    _NEPALI_AVAILABLE = True
except ImportError:
    _NEPALI_AVAILABLE = False
    logger.warning(
        "nepali_datetime package not installed — BS/AD conversion will be a no-op. "
        "Install it with: pip install nepali-datetime"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Core conversion functions
# ─────────────────────────────────────────────────────────────────────────────

def bs_str_to_ad(bs_str: Optional[str]) -> Optional[_date]:
    """
    Convert a BS date string (YYYY-MM-DD) to a Gregorian date.
    Returns None if the input is empty, None, or unparseable. Never raises.
    """
    if not bs_str or not isinstance(bs_str, str):
        return None
    bs_str = bs_str.strip()
    if not bs_str:
        return None
    if not _NEPALI_AVAILABLE:
        try:
            from datetime import datetime
            return datetime.strptime(bs_str, '%Y-%m-%d').date()
        except ValueError:
            return None
    try:
        parts = bs_str.split('-')
        if len(parts) != 3:
            return None
        y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
        np_date = _npdt.date(y, m, d)
        return np_date.to_datetime_date()
    except (ValueError, AttributeError, Exception) as exc:
        logger.debug("bs_str_to_ad failed for %r: %s", bs_str, exc)
        return None


def ad_date_to_bs_str(ad_date: Optional[_date]) -> str:
    """
    Convert a Gregorian date to a BS date string (YYYY-MM-DD).
    Returns '' if the input is None or conversion fails. Never raises.
    """
    if ad_date is None:
        return ''
    if not _NEPALI_AVAILABLE:
        return ad_date.strftime('%Y-%m-%d')
    try:
        return _npdt.date.from_datetime_date(ad_date).strftime('%Y-%m-%d')
    except (ValueError, AttributeError, Exception) as exc:
        logger.debug("ad_date_to_bs_str failed for %r: %s", ad_date, exc)
        return ad_date.strftime('%Y-%m-%d')


def parse_bs_date(bs_str: Optional[str], fallback: Optional[_date] = None) -> Optional[_date]:
    """Like bs_str_to_ad but returns *fallback* instead of None on failure."""
    result = bs_str_to_ad(bs_str)
    return result if result is not None else fallback


def today_bs() -> str:
    """Return today's date as a BS string (YYYY-MM-DD)."""
    return ad_date_to_bs_str(_date.today())


def get_active_fiscal_year(request):
    """
    Return the active FiscalYear for the current request's company, or None.
    Reads from request.session['active_fiscal_year_id'] first (set by the
    fiscal year selector view), then falls back to the current date match.
    """
    if request is None:
        return None
    try:
        from apps.company.models import FiscalYear
        company = getattr(request, 'user_company', None) or getattr(
            getattr(request, 'user', None), 'company', None
        )
        if not company:
            return None
        fy_id = request.session.get('active_fiscal_year_id')
        if fy_id:
            fy = FiscalYear.objects.filter(id=fy_id, company=company).first()
            if fy:
                return fy
        # Fallback: fiscal year that contains today
        return FiscalYear.get_current(company)
    except Exception as exc:
        logger.debug("get_active_fiscal_year failed: %s", exc)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Django form widget & field
# ─────────────────────────────────────────────────────────────────────────────

from django import forms  # noqa: E402


class NepaliDateWidget(forms.TextInput):
    """
    Drop-in replacement for forms.DateInput that renders a Nepali datepicker.
    Displays existing AD values as BS strings on edit.
    """

    def __init__(self, attrs=None):
        default_attrs = {
            'class': 'nepali-datepicker',
            'placeholder': 'YYYY-MM-DD',
            'autocomplete': 'off',
            # Fallback used by initNepaliDatePickers when the input value is empty
            # (e.g. error re-render where POST had no date because picker hadn't written it yet)
            'data-default-date': today_bs(),
        }
        if attrs:
            default_attrs.update(attrs)
        super().__init__(attrs=default_attrs)

    def format_value(self, value):
        if value is None:
            return ''
        if isinstance(value, _date):
            return ad_date_to_bs_str(value)
        return str(value)


class NepaliDateField(forms.Field):
    """
    Form field that accepts a BS date string and returns an AD datetime.date.

    Optionally validates that the date falls within a fiscal year:

        date = NepaliDateField(widget=NepaliDateWidget(), required=True)

    The fiscal year is injected at runtime by FiscalYearDateMixin.
    """

    widget = NepaliDateWidget

    def __init__(self, *args, required=True, **kwargs):
        kwargs.setdefault('required', required)
        super().__init__(*args, **kwargs)
        # Set by FiscalYearDateMixin at form init time
        self._fiscal_year = None

    def to_python(self, value):
        if not value:
            if self.required:
                raise forms.ValidationError('This field is required.')
            return None
        ad = bs_str_to_ad(value)
        if ad is None:
            raise forms.ValidationError(
                'Enter a valid BS date in YYYY-MM-DD format (e.g. 2081-01-15).'
            )
        # Fiscal year range check
        if self._fiscal_year is not None:
            fy = self._fiscal_year
            if fy.is_closed:
                raise forms.ValidationError(
                    f'Fiscal year {fy.name} is closed. No new transactions are allowed.'
                )
            if ad < fy.start_date or ad > fy.end_date:
                bs_start = ad_date_to_bs_str(fy.start_date)
                bs_end   = ad_date_to_bs_str(fy.end_date)
                raise forms.ValidationError(
                    f'Date must be within the active fiscal year '
                    f'{fy.name} ({bs_start} – {bs_end}).'
                )
        return ad

    def prepare_value(self, value):
        if isinstance(value, _date):
            return ad_date_to_bs_str(value)
        return value


# ─────────────────────────────────────────────────────────────────────────────
# Mixin — inject fiscal year into all NepaliDateFields on a form
# ─────────────────────────────────────────────────────────────────────────────

class FiscalYearDateMixin:
    """
    Mixin for ModelForms that have one or more NepaliDateField fields.

    Call self.inject_fiscal_year(request) at the end of __init__ to:
      1. Look up the active fiscal year for the user's company.
      2. Set _fiscal_year on every NepaliDateField so they validate
         that submitted dates fall within the fiscal year.
      3. Set the nepali-datepicker data attributes so the JS calendar
         is constrained to the fiscal year range.

    Usage:
        class MyForm(FiscalYearDateMixin, forms.ModelForm):
            date = NepaliDateField(widget=NepaliDateWidget(), required=True)

            def __init__(self, *args, **kwargs):
                self.request = kwargs.pop('request', None)
                super().__init__(*args, **kwargs)
                self.inject_fiscal_year(self.request)
    """

    def inject_fiscal_year(self, request):
        """Attach the active fiscal year to every NepaliDateField on this form."""
        fy = get_active_fiscal_year(request)
        if fy is None:
            return

        bs_start = ad_date_to_bs_str(fy.start_date)
        bs_end   = ad_date_to_bs_str(fy.end_date)

        for field in self.fields.values():
            if isinstance(field, NepaliDateField):
                field._fiscal_year = fy
                # Pass min/max to the widget so the JS datepicker can
                # visually restrict the selectable range
                field.widget.attrs.update({
                    'data-fy-start': bs_start,
                    'data-fy-end':   bs_end,
                    'data-fy-name':  fy.name or '',
                })
