from .views_collection.all_views import *
from .views_collection.list_view import billing_dashboard, invoice_list, credit_note_list, debit_note_list
from .htmx_views import InvoiceItemFormRowView, InvoiceItemProductsView, CollectPaymentHtmxView
from django.http import HttpResponse
from django.template.loader import render_to_string
from xhtml2pdf import pisa
from apps.utils.amount_words import amount_in_words as _amount_in_words
from apps.utils.decorator import auth_required
import os


@auth_required('billing.view_invoice')
def invoice_pdf_view(request, pk):
    if request.user.is_superuser:
        invoice = get_object_or_404(Invoice, pk=pk)
    else:
        invoice = get_object_or_404(Invoice, pk=pk, company=request.user.company)

    company = invoice.company
    amount_in_words = _amount_in_words(invoice.total)
    items = invoice.items.select_related('product', 'package').all()

    context = {
        'company': company,
        'company_name': company.name if company else "Your Company",
        'vat_number': company.vat_number if company else "",
        'address': company.address if company else "",
        'tel': company.phone if company else "",
        'email': company.email if company else "",
        'customer_name': invoice.customer.name if invoice.customer else "Cash",
        'customer_phone': invoice.customer.phone if invoice.customer else "",
        'customer_pan': (invoice.customer.pan_number or '') if invoice.customer else '',
        'invoice': invoice,
        'items': items,
        'amount_in_words': amount_in_words,
        'request': request,
        'vat_registered': company.vat_registered if company else False,
    }

    ebilling = company and company.enable_ebilling
    if ebilling:
        template = 'billing/invoices/invoice_pdf_ebilling.html'
        # Copy 1: Tax Invoice (seller's record), Copy 2: Invoice (customer), Copy 3: Invoice (office)
        context['copy_labels'] = [
            'ORIGINAL — TAX INVOICE (Seller Copy)',
            'DUPLICATE — INVOICE (Customer Copy)',
            'TRIPLICATE — INVOICE (Office Copy)',
        ]
    else:
        template = 'billing/invoices/invoice_pdf.html'

    html_string = render_to_string(template, context)

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'filename=invoice_{invoice.invoice_number}.pdf'

    pisa_status = pisa.CreatePDF(html_string, dest=response, encoding='UTF-8')

    if pisa_status.err:
        return HttpResponse('PDF generation error', status=500)

    return response


from django.http import JsonResponse
from django.contrib.auth.decorators import login_required

@login_required
def invoice_summary_api(request, pk):
    if request.user.is_superuser:
        invoice = get_object_or_404(Invoice, pk=pk)
    else:
        invoice = get_object_or_404(Invoice, pk=pk, company=request.user.company)

    return JsonResponse({
        'invoice_number': invoice.invoice_number or '',
        'customer_id': str(invoice.customer_id) if invoice.customer_id else '',
        'customer_name': invoice.customer.name if invoice.customer else 'Cash',
        'subtotal': str(invoice.subtotal),
        'discount': str(invoice.discount_amount),
        'tax': str(invoice.tax_amount),
        'total': str(invoice.total),
        'outstanding': str(invoice.outstanding_balance),
    })
