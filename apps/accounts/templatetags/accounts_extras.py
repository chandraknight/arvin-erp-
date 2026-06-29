from django import template

register = template.Library()

@register.filter
def replace(value, arg):
    """
    Replaces all occurrences of a substring with another string.
    Usage: {{ value|replace:"old_substring,new_substring" }}
    """
    if isinstance(value, str) and isinstance(arg, str):
        try:
            old, new = arg.split(',', 1)
            return value.replace(old, new)
        except ValueError:
            # Handle cases where arg doesn't contain a comma, or is empty
            return value
    return value 