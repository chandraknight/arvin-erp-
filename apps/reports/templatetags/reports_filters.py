from django import template

register = template.Library()

@register.filter(name='sub')
def sub(value, arg):
    """Subtracts the argument from the value."""
    try:
        return float(value) - float(arg)
    except (ValueError, TypeError):
        return '' # Return empty string or handle error as appropriate


@register.filter(name='dictkey')
def dictkey(d, key):
    """Looks up `key` in dict `d` — for use where the key is a template variable."""
    if not d:
        return None
    return d.get(key)