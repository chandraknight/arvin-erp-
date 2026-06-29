from django import template
from itertools import groupby
from operator import attrgetter
from apps.utils.nepali_date import ad_date_to_bs_str

register = template.Library()


@register.filter
def bs_date(value):
    """Convert an AD date/datetime object to a BS date string (YYYY-MM-DD)."""
    if value is None:
        return ''
    try:
        ad = value.date() if hasattr(value, 'date') else value
        return ad_date_to_bs_str(ad)
    except Exception:
        return str(value)

@register.filter
def get_value(obj, field_name):
    return getattr(obj, field_name, '')


@register.filter
def group_has_perm(user, perm_codename):
    if user.is_superuser:
        return True
    app_label, codename = perm_codename.split('.')
    return user.groups.filter(permissions__codename=codename,
                              permissions__content_type__app_label=app_label).exists() \
        or user.user_permissions.filter(codename=codename,
                                        content_type__app_label=app_label).exists()

@register.filter
def group_by(queryset, field_name):
    sorted_qs = sorted(queryset, key=attrgetter(field_name))
    return [(key, list(group)) for key, group in groupby(sorted_qs, key=attrgetter(field_name))]


@register.filter
def split(value, delimiter=','):
    return value.split(delimiter)


@register.filter
def mul(value, arg):
    try:
        return float(value) * float(arg)
    except (TypeError, ValueError):
        return ''


@register.filter
def get_account_color(account_type):
    color_map = {
        'ASSET': 'blue',
        'LIABILITY': 'purple',
        'EQUITY': 'indigo',
        'REVENUE': 'green',
        'EXPENSE': 'red',
    }
    return color_map.get(account_type, 'gray')
