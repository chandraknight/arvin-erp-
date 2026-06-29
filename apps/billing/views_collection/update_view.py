from ..forms import *
from django.shortcuts import redirect, render
from django.views.generic import UpdateView
from django.urls import reverse_lazy
from ..services.invoice_service import *
from .helper import *
from ...company.fiscal_year_guard import FiscalYearOpenMixin
from ...utils.mixins import AuthMixin
from django.core.exceptions import PermissionDenied
import logging

logger = logging.getLogger('audit')


class InvoiceUpdateView(AuthMixin, FiscalYearOpenMixin, UpdateView):
    model = Invoice
    form_class = InvoiceForm
    template_name = 'billing/invoices/invoice_form.html'
    permission_required = ['billing.change_invoice']

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if obj.is_locked:
            logger.warning(
                'INVOICE_UPDATE_BLOCKED invoice=%s status=%s actor=%s',
                obj.invoice_number, obj.status, self.request.user.email,
            )
            raise PermissionDenied(
                f"Invoice {obj.invoice_number} is {obj.status.lower()} and cannot be edited. "
                "Cancel it and issue a new invoice instead."
            )
        return obj

    def get_queryset(self):
        if self.request.user.is_superuser:
            return Invoice.objects.all()
        qs = Invoice.objects.filter(company=self.request.user.company)
        user_branch = getattr(self.request, 'user_branch', None)
        if user_branch is not None:
            qs = qs.filter(branch=user_branch)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['formset'] = InvoiceItemFormSet(self.request.POST, instance=self.object)
        else:
            context['formset'] = InvoiceItemFormSet(instance=self.object)
        company = getattr(self.request.user, 'company', None)
        context['vat_registered'] = company.vat_registered if company else False
        context['tax_rate'] = company.tax_rate if company else 0
        context['org_type'] = company.organisation_type if company else 'TRADING'
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        formset = context['formset']

        if formset.is_valid():
            self.object = form.save()
            formset.instance = self.object
            formset.save()

            calculate_total(self.object)
            self.object.save()

            return super().form_valid(form)
        else:
            return self.render_to_response(self.get_context_data(form=form))

    def get_success_url(self):
        return reverse_lazy('accounts:user_dashboard')


class VendorBillUpdateView(AuthMixin, FiscalYearOpenMixin, UpdateView):
    model = VendorBill
    form_class = VendorBillForm
    template_name = 'billing/vendor_bills/vendor_bill_form.html'
    permission_required = ['billing.change_vendorbill']

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if obj.is_locked:
            logger.warning(
                'VENDOR_BILL_UPDATE_BLOCKED bill=%s status=%s actor=%s',
                obj.bill_number, obj.status, self.request.user.email,
            )
            raise PermissionDenied(
                f"Vendor bill {obj.bill_number} is {obj.status.lower()} and cannot be edited. "
                "Cancel it and issue a new bill instead."
            )
        return obj

    def get_queryset(self):
        if self.request.user.is_superuser:
            return VendorBill.objects.all()
        qs = VendorBill.objects.filter(vendor__company=self.request.user.company)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['formset'] = VendorBillItemFormSet(self.request.POST, instance=self.object)
        else:
            context['formset'] = VendorBillItemFormSet(instance=self.object)
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        formset = context['formset']

        if formset.is_valid():
            self.object = form.save()
            formset.instance = self.object
            formset.save()

            update_vendor_bill_total(self.object)
            self.object.save()

            return super().form_valid(form)
        else:
            return self.render_to_response(self.get_context_data(form=form))

    def get_success_url(self):
        return reverse_lazy('accounts:user_dashboard')


class CreditNoteUpdateView(AuthMixin, FiscalYearOpenMixin, NoteCreateUpdateMixin, UpdateView):
    model = CreditNote
    form_class = CreditNoteForm
    template_name = 'billing/notes/credit_note_form.html'
    permission_required = ['billing.change_creditnote']

    def get_queryset(self):
        if self.request.user.is_superuser:
            return CreditNote.objects.all()
        qs = CreditNote.objects.filter(company=self.request.user.company)
        user_branch = getattr(self.request, 'user_branch', None)
        if user_branch is not None:
            qs = qs.filter(branch=user_branch)
        return qs

    def get_success_url(self):
        return reverse_lazy('accounts:user_dashboard')


class DebitNoteUpdateView(AuthMixin, FiscalYearOpenMixin, NoteCreateUpdateMixin, UpdateView):
    model = DebitNote
    form_class = DebitNoteForm
    template_name = 'billing/notes/credit_note_form.html'
    permission_required = ['billing.change_debitnote']

    def get_queryset(self):
        if self.request.user.is_superuser:
            return DebitNote.objects.all()
        qs = DebitNote.objects.filter(company=self.request.user.company)
        user_branch = getattr(self.request, 'user_branch', None)
        if user_branch is not None:
            qs = qs.filter(branch=user_branch)
        return qs

    def get_success_url(self):
        return reverse_lazy('accounts:user_dashboard')
