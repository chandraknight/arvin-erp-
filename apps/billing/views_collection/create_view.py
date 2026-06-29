from django.contrib import messages
from django.http import HttpResponseRedirect

from ..forms import *
from django.shortcuts import redirect, render
from django.views.generic import CreateView, UpdateView
from django.urls import reverse_lazy, reverse
from ..services.invoice_service import *
from django.db import transaction
from .helper import *
from ...company.fiscal_year_guard import FiscalYearOpenMixin
from ...utils.mixins import AuthMixin


class InvoiceCreateView(AuthMixin, FiscalYearOpenMixin, CreateView):
    model = Invoice
    form_class = InvoiceForm
    template_name = 'billing/invoices/invoice_form.html'
    permission_required = ['billing.add_invoice']

    def get_context_data(self, **kwargs):
        from apps.utils.constant import PAYMENT_METHOD_CHOICES
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['formset'] = InvoiceItemFormSet(self.request.POST, request=self.request)
        else:
            context['formset'] = InvoiceItemFormSet(request=self.request)
        company = getattr(self.request.user, 'company', None)
        context['org_type'] = company.organisation_type if company else 'TRADING'
        context['vat_registered'] = company.vat_registered if company else False
        context['tax_rate'] = company.tax_rate if company else 0
        context['payment_method_choices'] = PAYMENT_METHOD_CHOICES
        # Preview next invoice number (read-only — doesn't reserve it)
        if company:
            try:
                next_inv, _ = generate_invoice_number(company.id)
                context['next_invoice_number'] = next_inv
            except Exception:
                context['next_invoice_number'] = None
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        formset = context['formset']

        if form.is_valid() and formset.is_valid():
            try:
                with transaction.atomic():
                    # Ensure company is set
                    if hasattr(self.request.user, 'company'):
                        form.instance.company = self.request.user.company

                    # Stamp branch — branch-assigned users can only create
                    # invoices for their own branch.
                    user_branch = getattr(self.request, 'user_branch', None)
                    if user_branch is not None:
                        form.instance.branch = user_branch

                    # Handle action (Issue vs Pending)
                    action = self.request.POST.get('action', 'issue')
                    company = getattr(self.request.user, 'company', None)
                    is_non_vat = company and not company.vat_registered

                    if action == 'issue':
                        if not form.instance.invoice_number:
                            doc_type = 'ORD' if is_non_vat else 'INV'
                            invoice_number, seq_number = generate_invoice_number(self.request.user.company.id, doc_type=doc_type)
                            form.instance.invoice_number = invoice_number
                            form.instance.sequence_number = seq_number
                        # Non-VAT companies: treat as estimate — no journal, no AR impact
                        form.instance.status = 'ESTIMATE' if is_non_vat else 'ISSUED'
                    else:
                        # Save as draft — no invoice number assigned yet
                        form.instance.status = 'DRAFT'

                    # Handle BS Date — NepaliDateField returns a datetime.date already
                    due_date_bs = form.cleaned_data.get('due_date_bs')
                    if due_date_bs:
                        import datetime
                        if isinstance(due_date_bs, datetime.date):
                            form.instance.due_date = due_date_bs
                        else:
                            try:
                                import nepali_datetime
                                form.instance.due_date = nepali_datetime.datetime.strptime(
                                    str(due_date_bs), '%Y-%m-%d'
                                ).to_datetime_date()
                            except (ValueError, AttributeError):
                                pass

                    # Prevent the post_save signal from firing post_invoice_journal
                    # prematurely — we call it once explicitly below with final totals.
                    form.instance._skip_journal = True
                    self.object = form.save()
                    formset.instance = self.object
                    formset.save()

                    # Recalculate totals and persist (queryset update — no post_save signal)
                    calculate_total(self.object)
                    is_estimate = self.object.status == 'ESTIMATE'
                    Invoice.objects.filter(pk=self.object.pk).update(
                        subtotal=self.object.subtotal,
                        discount_amount=self.object.discount_amount,
                        tax_amount=self.object.tax_amount,
                        total=self.object.total,
                        outstanding_balance=0 if is_estimate else self.object.total,
                    )
                    self.object.outstanding_balance = 0 if is_estimate else self.object.total

                    # Now post the journal entry once, with the final correct total
                    # Estimates (non-VAT companies) do not create journal entries.
                    if action == 'issue' and not is_estimate and self.object.invoice_number and self.object.total > 0:
                        from apps.bookkeeping.db_functions import post_invoice_journal
                        post_invoice_journal(self.object.id)

                    # Submit to IRD CBMS if e-billing is enabled for this company
                    if action == 'issue' and not is_estimate and self.object.invoice_number:
                        company = getattr(self.request.user, 'company', None)
                        if company and company.enable_ebilling:
                            from apps.billing.services.cbms_service import post_bill
                            cbms_log = post_bill(self.object)
                            if cbms_log and not cbms_log.success:
                                messages.warning(
                                    self.request,
                                    f"Invoice issued but CBMS submission failed (code {cbms_log.response_code}). "
                                    f"Please resubmit from the invoice detail page."
                                )

                    # Handle Payment Collection — not applicable for estimates
                    collect_payment = form.cleaned_data.get('collect_payment', False)
                    if collect_payment and action == 'issue' and not is_estimate:
                        from apps.payments.services.payment_services import create_invoice_payment
                        from apps.utils.constant import PAYMENT_METHOD_CHOICES
                        valid_methods = [m[0] for m in PAYMENT_METHOD_CHOICES]

                        # Build list of (method, amount) from primary row + split rows
                        payment_rows = []
                        primary_method = form.cleaned_data.get('payment_method')
                        primary_amount = form.cleaned_data.get('payment_amount')
                        if primary_method and primary_amount:
                            payment_rows.append((primary_method, primary_amount))

                        extra_methods = self.request.POST.getlist('extra_payment_method')
                        extra_amounts = self.request.POST.getlist('extra_payment_amount')
                        for method, raw_amount in zip(extra_methods, extra_amounts):
                            method = method.strip()
                            if method not in valid_methods:
                                continue
                            try:
                                from decimal import Decimal
                                amt = Decimal(raw_amount)
                                if amt > 0:
                                    payment_rows.append((method, amt))
                            except Exception:
                                pass

                        if payment_rows:
                            created_payments = []
                            for method, amount in payment_rows:
                                try:
                                    with transaction.atomic():
                                        success, payment_obj, error = create_invoice_payment(
                                            request=self.request,
                                            invoice=self.object,
                                            payment_method=method,
                                            payment_amount=amount,
                                            payment_reference=form.cleaned_data.get('payment_reference'),
                                            payment_date=form.cleaned_data.get('payment_date'),
                                            payment_description=form.cleaned_data.get('payment_description', ''),
                                        )
                                        if not success:
                                            raise Exception(error)
                                        created_payments.append(payment_obj)
                                except Exception as payment_error:
                                    messages.warning(self.request, f"Payment ({method}) failed: {payment_error}")
                                    break
                            if len(created_payments) > 1:
                                from apps.payments.services.payment_services import consolidate_split_payment_journals
                                consolidate_split_payment_journals(created_payments)
                            self.object.refresh_from_db()
                        else:
                            messages.warning(self.request, "Payment method and amount are required to collect payment.")
                    else:
                        # No immediate payment — outstanding equals invoice total
                        self.object.outstanding_balance = self.object.total

                    # Queryset update avoids firing post_save again, which would
                    # re-run post_invoice_journal and corrupt the journal entry.
                    Invoice.objects.filter(pk=self.object.pk).update(
                        outstanding_balance=self.object.outstanding_balance
                    )

                    messages.success(self.request, f"Invoice {self.object.invoice_number or 'Pending'} created successfully.")
                    
                    if action == 'issue' and self.request.POST.get('skip_pdf_redirect') != '1':
                        return render(self.request, 'billing/invoices/pdf_redirect.html', {
                            'pdf_url': reverse('billing:invoice_pdf', kwargs={'pk': self.object.pk}),
                            'redirect_url': self.get_success_url(),
                            'invoice': self.object
                        })
                        
                    return redirect(self.get_success_url())
            except Exception as e:
                messages.error(self.request, f"Error saving invoice: {str(e)}")
                return self.form_invalid(form)
        
        return self.render_to_response(self.get_context_data(form=form))

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request'] = self.request
        return kwargs

    def get_success_url(self):
        # return reverse_lazy('invoices:invoice_detail', kwargs={'pk': self.object.pk})
        return reverse_lazy('accounts:user_dashboard')


class VendorBillCreateView(AuthMixin, FiscalYearOpenMixin, CreateView):
    model = VendorBill
    form_class = VendorBillForm
    template_name = 'billing/vendor_bills/vendor_bill_form.html'
    permission_required = ['billing.add_vendorbill']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['formset'] = VendorBillItemFormSet(self.request.POST, request=self.request)
        else:
            context['formset'] = VendorBillItemFormSet(request=self.request)
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        formset = context['formset']

        if formset.is_valid():
            with transaction.atomic():
                company = getattr(self.request.user, 'company', None)
                if company:
                    form.instance.company = company

                user_branch = getattr(self.request, 'user_branch', None)
                if user_branch is not None:
                    form.instance.branch = user_branch

                if not form.instance.status:
                    form.instance.status = 'DRAFT'

                self.object = form.save()

                # Auto-assign debit_account (Purchases expense account) for each item
                from apps.bookkeeping.models import LedgerAccount
                default_account = None
                if company:
                    default_account = (
                        LedgerAccount.objects.filter(company=company, name='Purchases', account_type='EXPENSE').first()
                        or LedgerAccount.objects.filter(company=company, account_type='EXPENSE', is_deleted=False).first()
                    )

                items = formset.save(commit=False)
                for item in items:
                    item.vendor_bill = self.object
                    if not item.debit_account_id and default_account:
                        item.debit_account = default_account
                    item.save()
                for obj in formset.deleted_objects:
                    obj.delete()

                update_vendor_bill_total(self.object)
                self.object.save()

                # Record payment if requested
                collect = form.cleaned_data.get('collect_payment', False)
                if collect:
                    from apps.payments.models import VendorPayment
                    from apps.utils.constant import PAYMENT_METHOD_CHOICES
                    from django.utils import timezone
                    from decimal import Decimal as D

                    valid_methods = [m[0] for m in PAYMENT_METHOD_CHOICES]
                    payment_date_ad = form.cleaned_data.get('payment_date') or timezone.now().date()

                    payment_rows = []
                    primary_method = form.cleaned_data.get('payment_method')
                    primary_amount = form.cleaned_data.get('payment_amount')
                    if primary_method and primary_amount and primary_amount > 0:
                        payment_rows.append((primary_method, primary_amount))

                    extra_methods = self.request.POST.getlist('extra_payment_method')
                    extra_amounts = self.request.POST.getlist('extra_payment_amount')
                    for method, raw in zip(extra_methods, extra_amounts):
                        method = method.strip()
                        if method not in valid_methods:
                            continue
                        try:
                            amt = D(raw)
                            if amt > 0:
                                payment_rows.append((method, amt))
                        except Exception:
                            pass

                    if payment_rows:
                        for method, amount in payment_rows:
                            VendorPayment.objects.create(
                                vendor_bill=self.object,
                                amount=amount,
                                payment_date=payment_date_ad,
                                payment_method=method,
                            )
                        self.object.status = 'PAID'
                        self.object.save(update_fields=['status'])
                        total_paid = sum(a for _, a in payment_rows)
                        messages.success(self.request, f'Vendor bill created and payment of ₹{total_paid} recorded.')
                    else:
                        messages.success(self.request, 'Vendor bill created successfully.')
                else:
                    messages.success(self.request, 'Vendor bill created successfully.')

            return super().form_valid(form)
        else:
            return self.render_to_response(self.get_context_data(form=form))

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request'] = self.request
        return kwargs

    def get_success_url(self):
        # return reverse_lazy('vendor_bills:vendor_bill_detail', kwargs={'pk': self.object.pk})
        return reverse_lazy('accounts:user_dashboard')


class CreditNoteCreateView(AuthMixin, NoteCreateUpdateMixin, CreateView):
    model = CreditNote
    form_class = CreditNoteForm
    template_name = 'billing/notes/credit_note_form.html'
    permission_required = ['billing.add_creditnote']

    def get_template_names(self):
        if self.request.headers.get("HX-Request") == "true" or self.request.GET.get("modal") == "1":
            return ["billing/partials/credit_note_form_modal.html"]
        return [self.template_name]

    def get_success_url(self):
        return reverse_lazy('accounts:user_dashboard')


class DebitNoteCreateView(AuthMixin, NoteCreateUpdateMixin, CreateView):
    model = DebitNote
    form_class = DebitNoteForm
    template_name = 'billing/notes/debit_note_form.html'
    permission_required = ['billing.add_debitnote']

    def get_template_names(self):
        if self.request.headers.get("HX-Request") == "true" or self.request.GET.get("modal") == "1":
            return ["billing/partials/debit_note_form_modal.html"]
        return [self.template_name]

    def get_success_url(self):
        return reverse_lazy('accounts:user_dashboard')
