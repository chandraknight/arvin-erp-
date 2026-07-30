from django import template

register = template.Library()

@register.filter(name='sub')
def sub(value, arg):
    """Subtracts the argument from the value."""
    try:
        return float(value) - float(arg)
    except (ValueError, TypeError):
        return '' # Return empty string or handle error as appropriate 