from django.contrib import messages
from django.shortcuts import render, get_object_or_404, redirect
from ...utils.decorator import auth_required
from ...utils.amount_words import amount_in_words
from ..models import Invoice


@auth_required('billing.view_invoice')
def invoice_detail(request, pk):
    # Scope to the user's company to prevent cross-tenant access
    if request.user.is_superuser:
        invoice = get_object_or_404(Invoice, pk=pk)
    else:
        invoice = get_object_or_404(Invoice, pk=pk, company=request.user.company)
        # Branch isolation — a branch-assigned user may only view their branch's invoices
        user_branch = getattr(request, 'user_branch', None)
        if user_branch is not None and invoice.branch != user_branch:
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied('You do not have access to this invoice.')

    items = invoice.items.select_related('product', 'package').all()
    company = invoice.company
    return render(request, 'billing/invoices/invoice_detail.html', {
        'invoice': invoice,
        'items': items,
        'vat_registered': company.vat_registered if company else False,
        'amount_in_words': amount_in_words(invoice.total),
    })
