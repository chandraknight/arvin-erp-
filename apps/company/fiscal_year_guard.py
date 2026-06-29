"""
Fiscal Year Lock Guard
======================
Provides a decorator and a utility function to block write operations
(create / update / delete) when the active fiscal year is closed.

Usage in views:
    from apps.company.fiscal_year_guard import fiscal_year_open_required

    @fiscal_year_open_required
    def create_invoice(request):
        ...

For class-based views, mix in FiscalYearOpenMixin:
    class InvoiceCreateView(FiscalYearOpenMixin, CreateView):
        ...
"""

from functools import wraps
from django.contrib import messages
from django.shortcuts import redirect
from django.http import JsonResponse
from .models import FiscalYear


def get_active_fiscal_year(request):
    """Return the FiscalYear currently active in the session, or None."""
    fy_id = request.session.get('active_fiscal_year_id')
    if not fy_id:
        return None
    company = getattr(request.user, 'company', None)
    if not company:
        return None
    return FiscalYear.objects.filter(id=fy_id, company=company).first()


def is_fiscal_year_closed(request):
    """Return True if the active fiscal year is closed."""
    fy = get_active_fiscal_year(request)
    return fy is not None and fy.is_closed


def fiscal_year_open_required(view_func):
    """
    Decorator for function-based views.
    Blocks the view if the active fiscal year is closed.
    Returns JSON error for AJAX requests, redirects otherwise.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if is_fiscal_year_closed(request):
            fy = get_active_fiscal_year(request)
            msg = (
                f"Fiscal year {fy.name} is closed. "
                "No new transactions or edits are allowed. "
                "Please select an open fiscal year."
            )
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or \
               request.content_type == 'application/json':
                return JsonResponse({'success': False, 'error': msg}, status=403)
            messages.error(request, msg)
            return redirect(request.META.get('HTTP_REFERER', 'billing:invoice_list'))
        return view_func(request, *args, **kwargs)
    return wrapper


class FiscalYearOpenMixin:
    """
    Mixin for class-based views.
    Blocks dispatch if the active fiscal year is closed.
    """
    def dispatch(self, request, *args, **kwargs):
        if is_fiscal_year_closed(request):
            fy = get_active_fiscal_year(request)
            msg = (
                f"Fiscal year {fy.name} is closed. "
                "No new transactions or edits are allowed."
            )
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': msg}, status=403)
            messages.error(request, msg)
            return redirect(request.META.get('HTTP_REFERER', 'billing:invoice_list'))
        return super().dispatch(request, *args, **kwargs)
