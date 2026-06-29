from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy
from django.views.generic import CreateView, UpdateView
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from ..forms import JournalEntryForm, JournalEntryLineFormSet, LedgerAccountForm
from ..models import JournalEntry, LedgerAccount
from ...company.models import Company
from ...utils.mixins import AuthMixin
from ...company.fiscal_year_guard import FiscalYearOpenMixin


class JournalEntryCreateView(AuthMixin, FiscalYearOpenMixin, CreateView):
    model = JournalEntry
    form_class = JournalEntryForm
    template_name = 'bookkeeping/journal_entry_form.html'
    success_url = reverse_lazy('bookkeeping:journal_entry_list')
    permission_required = ['bookkeeping.add_journalentry']

    def get(self, request, *args, **kwargs):
        form = self.form_class(request=self.request)
        formset = JournalEntryLineFormSet(request=self.request)
        return render(self.request, self.template_name, {'form': form, 'formset': formset})

    def post(self, request, *args, **kwargs):
        form = self.form_class(request.POST, request=self.request)
        formset = JournalEntryLineFormSet(request.POST, request=self.request)

        formset.empty_form.request =self.request
        if form.is_valid() and formset.is_valid():
            # Compute totals from valid formset lines before saving
            total_debit = Decimal('0.00')
            total_credit = Decimal('0.00')
            for f in formset.forms:
                if f.cleaned_data and not f.cleaned_data.get('DELETE', False):
                    total_debit += f.cleaned_data.get('debit_amount') or Decimal('0.00')
                    total_credit += f.cleaned_data.get('credit_amount') or Decimal('0.00')

            if total_debit != total_credit or total_debit == Decimal('0.00'):
                from django.contrib import messages as msg
                msg.error(
                    request,
                    f"Journal entry is not balanced — Debit {total_debit} ≠ Credit {total_credit}. "
                    "Total debits must equal total credits and cannot be zero."
                )
                return render(request, self.template_name, {'form': form, 'formset': formset})

            journal_entry = form.save(commit=False)
            journal_entry.company = request.user.company
            journal_entry.created_by = request.user
            journal_entry.save()
            formset.instance = journal_entry
            formset.save()
            from django.contrib import messages as msg
            msg.success(request, f"Journal entry created — {journal_entry.description or journal_entry.pk}.")
            return redirect(self.success_url)
        return render(request, self.template_name, {'form': form, 'formset': formset})


class LedgerAccountCreateView(AuthMixin,CreateView):
    model = LedgerAccount
    form_class = LedgerAccountForm
    template_name = 'bookkeeping/ledger_account_form.html'
    permission_required = ['bookkeeping.add_ledgeraccount']

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        company = self.request.user.company
        kwargs['company'] = company
        return kwargs

    def get_success_url(self):
        return reverse_lazy('bookkeeping:ledger_account_list')

# ─── NFRS 13 Fixed Asset views ────────────────────────────────────────────

from django import forms as dj_forms
from ..models import FixedAsset, FixedAssetDepreciationLog
from ..fixed_asset_service import post_depreciation, depreciation_schedule
from django.contrib import messages
from django.views.generic import ListView, DetailView
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from apps.utils.nepali_date import NepaliDateWidget, NepaliDateField


class FixedAssetForm(dj_forms.ModelForm):
    acquisition_date = NepaliDateField(widget=NepaliDateWidget(), required=True, label='Acquisition Date (BS)')

    class Meta:
        model = FixedAsset
        fields = [
            'name', 'asset_code', 'description', 'category',
            'cost', 'residual_value', 'useful_life_years',
            'depreciation_method', 'depreciation_rate',
            'acquisition_date', 'status',
            'asset_account', 'accumulated_dep_account', 'depreciation_expense_account',
        ]
        widgets = {
            'description': dj_forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        from ..models import LedgerAccount
        if company:
            qs = LedgerAccount.objects.filter(company=company, is_deleted=False)
            self.fields['asset_account'].queryset              = qs.filter(account_type='ASSET')
            self.fields['accumulated_dep_account'].queryset   = qs.filter(account_type='ASSET')
            self.fields['depreciation_expense_account'].queryset = qs.filter(account_type='EXPENSE')
        for f in ['asset_account', 'accumulated_dep_account', 'depreciation_expense_account']:
            self.fields[f].required = False


@method_decorator(login_required, name='dispatch')
class FixedAssetCreateView(AuthMixin, CreateView):
    model = FixedAsset
    form_class = FixedAssetForm
    template_name = 'bookkeeping/fixed_asset_form.html'
    permission_required = ['bookkeeping.add_fixedasset']

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw['company'] = self.request.user_company
        return kw

    def form_valid(self, form):
        form.instance.company = self.request.user_company
        form.instance.created_by = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('bookkeeping:fixed_asset_detail', kwargs={'pk': self.object.pk})


@method_decorator(login_required, name='dispatch')
class FixedAssetListView(AuthMixin, ListView):
    model = FixedAsset
    template_name = 'bookkeeping/fixed_asset_list.html'
    context_object_name = 'assets'
    permission_required = ['bookkeeping.view_fixedasset']

    def get_queryset(self):
        return FixedAsset.objects.filter(
            company=self.request.user_company, is_deleted=False
        ).order_by('category', 'name')


@method_decorator(login_required, name='dispatch')
class FixedAssetDetailView(AuthMixin, DetailView):
    model = FixedAsset
    template_name = 'bookkeeping/fixed_asset_detail.html'
    permission_required = ['bookkeeping.view_fixedasset']

    def get_queryset(self):
        return FixedAsset.objects.filter(company=self.request.user_company)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['schedule'] = depreciation_schedule(self.object)
        ctx['logs'] = self.object.depreciation_logs.select_related('journal_entry').order_by('-period_end')
        return ctx

    def post(self, request, *args, **kwargs):
        asset = self.get_object()
        period_start_str = request.POST.get('period_start')
        period_end_str   = request.POST.get('period_end')
        from datetime import date
        try:
            from apps.utils.nepali_date import bs_str_to_ad
            period_start = bs_str_to_ad(period_start_str) if period_start_str else date.today().replace(day=1)
            period_end   = bs_str_to_ad(period_end_str)   if period_end_str   else date.today()
            log = post_depreciation(asset, period_start, period_end, posted_by=request.user)
            messages.success(request, f"Depreciation NPR {log.amount:,.2f} posted for {asset.name}.")
        except ValueError as e:
            messages.error(request, str(e))
        return redirect('bookkeeping:fixed_asset_detail', pk=asset.pk)


@method_decorator(login_required, name='dispatch')
class FixedAssetUpdateView(AuthMixin, UpdateView):
    model = FixedAsset
    form_class = FixedAssetForm
    template_name = 'bookkeeping/fixed_asset_form.html'
    permission_required = ['bookkeeping.change_fixedasset']

    def get_queryset(self):
        return FixedAsset.objects.filter(
            company=self.request.user_company, is_deleted=False
        )

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw['company'] = self.request.user_company
        return kw

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        messages.success(self.request, f"Asset '{self.object.name}' updated.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('bookkeeping:fixed_asset_detail', kwargs={'pk': self.object.pk})


@login_required
def fixed_asset_dispose(request, pk):
    """Mark a fixed asset as DISPOSED and record disposal date."""
    from django.contrib.auth.decorators import login_required
    from ..models import FixedAsset
    asset = get_object_or_404(FixedAsset, pk=pk, company=request.user_company, is_deleted=False)

    if asset.status == 'DISPOSED':
        messages.error(request, "Asset is already disposed.")
        return redirect('bookkeeping:fixed_asset_detail', pk=pk)

    if request.method == 'POST':
        from datetime import date as _date
        from apps.utils.nepali_date import bs_str_to_ad
        disposal_date_str = request.POST.get('disposal_date', '')
        disposal_date = bs_str_to_ad(disposal_date_str) if disposal_date_str else _date.today()
        asset.status = 'DISPOSED'
        asset.disposal_date = disposal_date
        asset.updated_by = request.user
        asset.save(update_fields=['status', 'disposal_date', 'updated_by'])
        messages.success(request, f"Asset '{asset.name}' marked as disposed on {disposal_date}.")
        return redirect('bookkeeping:fixed_asset_detail', pk=pk)

    return render(request, 'bookkeeping/fixed_asset_dispose.html', {'asset': asset})
