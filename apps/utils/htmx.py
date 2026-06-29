"""
apps/utils/htmx.py
==================
Shared utilities for HTMX views across all apps.

Usage
-----
    from apps.utils.htmx import htmx_response, is_htmx, toast_response

    # In a view:
    if is_htmx(request):
        return htmx_response(request, 'app/partials/row.html', context)

    # After a mutating action, send a toast + optional redirect:
    return toast_response('Invoice saved.', level='success',
                          redirect_url=reverse('billing:invoice_list'))
"""

from __future__ import annotations

import json
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.shortcuts import render


def is_htmx(request) -> bool:
    """Return True if the request was made by HTMX."""
    return request.headers.get('HX-Request') == 'true'


def htmx_or_full(request, template: str, partial_template: str, context: dict) -> HttpResponse:
    """
    Return a partial template for HTMX requests, full page for normal requests.

    Example:
        return htmx_or_full(request,
            'billing/invoice_list.html',
            'billing/partials/invoice_table.html',
            {'invoices': qs})
    """
    if is_htmx(request):
        return render(request, partial_template, context)
    return render(request, template, context)


def htmx_response(request, template: str, context: dict,
                  status: int = 200) -> HttpResponse:
    """Render a partial template and return it as an HttpResponse."""
    html = render_to_string(template, context, request=request)
    return HttpResponse(html, status=status)


def toast_trigger(level: str, message: str) -> dict:
    """
    Build the HX-Trigger header value for a toast notification.

    The base.html 'showToast' event listener picks this up and renders
    a toast without a page reload.

    Usage:
        response = HttpResponse(...)
        response['HX-Trigger'] = json.dumps(toast_trigger('success', 'Saved!'))
        return response
    """
    return {'showToast': {'level': level, 'message': message}}


def htmx_redirect(url: str, message: str = '', level: str = 'success') -> HttpResponse:
    """
    Return an HTMX response that redirects the browser to *url*.

    Optionally triggers a toast notification after the redirect.
    Uses HX-Redirect header which HTMX handles as a full navigation.
    """
    response = HttpResponse(status=204)
    response['HX-Redirect'] = url
    if message:
        response['HX-Trigger'] = json.dumps(toast_trigger(level, message))
    return response


def htmx_refresh(message: str = '', level: str = 'success') -> HttpResponse:
    """
    Tell HTMX to do a full page refresh.
    Optionally triggers a toast before the refresh.
    """
    response = HttpResponse(status=204)
    response['HX-Refresh'] = 'true'
    if message:
        response['HX-Trigger'] = json.dumps(toast_trigger(level, message))
    return response


def empty_response(message: str = '', level: str = 'success') -> HttpResponse:
    """
    Return an empty 204 response, optionally with a toast trigger.
    Useful for delete actions where the row is removed by HTMX hx-swap="outerHTML".
    """
    response = HttpResponse(status=204)
    if message:
        response['HX-Trigger'] = json.dumps(toast_trigger(level, message))
    return response
