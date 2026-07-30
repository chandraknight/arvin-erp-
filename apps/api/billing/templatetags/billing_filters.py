from django import template
from apps.utils.nepali_date import ad_date_to_bs_str

register = template.Library()


@register.filter
def to_bs(value):
    """Convert an AD date/datetime to a BS date string (YYYY-MM-DD). Returns '' on failure."""
    if not value:
        return ''
    try:
        from datetime import date, datetime
        if isinstance(value, datetime):
            value = value.date()
        if isinstance(value, date):
            return ad_date_to_bs_str(value)
    except Exception:
        pass
    return str(value)

@register.filter
def mul(value, arg):
    """Multiplies the value by the argument."""
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return '' 