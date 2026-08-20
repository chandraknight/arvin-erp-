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


# ─── Nepal TDS rates ───────────────────────────────────────────────────────

from django.views.generic import ListView
from ..forms import TDSRateForm
from ..models import TDSRate


class TDSRateListView(AuthMixin, ListView):
    model = TDSRate
    template_name = 'bookkeeping/tds_rate_list.html'
    context_object_name = 'tds_rates'
    paginate_by = 20
    permission_required = ['bookkeeping.view_tdsrate']

    def get_queryset(self):
        return TDSRate.objects.filter(
            company=self.request.user_company, is_deleted=False
        ).order_by('category', '-effective_from')


class TDSRateCreateView(AuthMixin, CreateView):
    model = TDSRate
    form_class = TDSRateForm
    template_name = 'bookkeeping/tds_rate_form.html'
    permission_required = ['bookkeeping.add_tdsrate']
    success_url = reverse_lazy('bookkeeping:tds_rate_list')

    def form_valid(self, form):
        form.instance.company = self.request.user_company
        form.instance.created_by = self.request.user
        return super().form_valid(form)


class TDSRateUpdateView(AuthMixin, UpdateView):
    model = TDSRate
    form_class = TDSRateForm
    template_name = 'bookkeeping/tds_rate_form.html'
    permission_required = ['bookkeeping.change_tdsrate']
    success_url = reverse_lazy('bookkeeping:tds_rate_list')

    def get_queryset(self):
        return TDSRate.objects.filter(company=self.request.user_company, is_deleted=False)

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        return super().form_valid(form)

# ─── NFRS 13 Fixed Asset views ────────────────────────────────────────────

from django import forms as dj_forms
from ..models import FixedAsset, FixedAssetDepreciationLog
from ..fixed_asset_service import post_depreciation, post_disposal, depreciation_schedule
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
    """
    NFRS 13 (IAS 16) disposal: derecognize the asset and post gain/loss on
    disposal via post_disposal() — previously this only flipped a status flag
    with no journal entry, leaving cost and accumulated depreciation on the
    books forever and any gain/loss unrecognized.
    """
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
        sale_proceeds = Decimal(request.POST.get('sale_proceeds') or '0')
        try:
            post_disposal(asset, disposal_date, sale_proceeds, posted_by=request.user)
            messages.success(request, f"Asset '{asset.name}' disposed on {disposal_date}.")
        except ValueError as e:
            messages.error(request, str(e))
            return redirect('bookkeeping:fixed_asset_dispose', pk=pk)
        return redirect('bookkeeping:fixed_asset_detail', pk=pk)

    return render(request, 'bookkeeping/fixed_asset_dispose.html', {'asset': asset})


# ─── NFRS 1 Prepaid Expense views ─────────────────────────────────────────

from datetime import datetime
from django.contrib.auth.decorators import login_required as _login_required
from ...utils.constant import RUPEE


def _parse_ad_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except ValueError:
        return None


@_login_required
def prepaid_expense_list(request):
    from ..models import PrepaidExpense
    company = request.user_company
    if not company:
        messages.warning(request, "Your account is not associated with a company.")
        return redirect('accounts:user_dashboard')

    prepaid_expenses = PrepaidExpense.objects.filter(
        company=company, is_deleted=False
    ).order_by('-start_date')

    return render(request, 'bookkeeping/prepaid_expense_list.html', {
        'prepaid_expenses': prepaid_expenses,
        'currency_symbol': RUPEE,
    })


@_login_required
def prepaid_expense_create(request):
    from ..prepaid_expense_service import create_prepaid_expense

    company = request.user_company
    if not company:
        messages.warning(request, "Your account is not associated with a company.")
        return redirect('accounts:user_dashboard')

    bank_cash_accounts = LedgerAccount.objects.filter(
        company=company, account_type='ASSET', is_deleted=False
    ).order_by('name')

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        amount_str = request.POST.get('total_amount', '').strip()
        start_date_str = request.POST.get('start_date', '').strip()
        end_date_str = request.POST.get('end_date', '').strip()
        paid_from_id = request.POST.get('paid_from_account')

        paid_from_account = bank_cash_accounts.filter(pk=paid_from_id).first()
        try:
            total_amount = Decimal(amount_str)
            start_date = _parse_ad_date(start_date_str)
            end_date = _parse_ad_date(end_date_str)
            if not name or total_amount <= 0 or not start_date or not end_date or not paid_from_account:
                raise ValueError
        except (Exception,):
            messages.error(request, "Fill in all fields with valid values.")
            return render(request, 'bookkeeping/prepaid_expense_form.html', {'bank_cash_accounts': bank_cash_accounts})

        try:
            prepaid = create_prepaid_expense(
                company=company, name=name, total_amount=total_amount,
                start_date=start_date, end_date=end_date,
                paid_from_account=paid_from_account, description=description,
                created_by=request.user,
            )
        except ValueError as exc:
            messages.error(request, str(exc))
            return render(request, 'bookkeeping/prepaid_expense_form.html', {'bank_cash_accounts': bank_cash_accounts})

        messages.success(request, f"Prepaid expense '{prepaid.name}' recorded.")
        return redirect('bookkeeping:prepaid_expense_detail', pk=prepaid.pk)

    return render(request, 'bookkeeping/prepaid_expense_form.html', {'bank_cash_accounts': bank_cash_accounts})


@_login_required
def prepaid_expense_detail(request, pk):
    from ..models import PrepaidExpense
    company = request.user_company
    qs = PrepaidExpense.objects.filter(is_deleted=False)
    if not request.user.is_superuser and company:
        qs = qs.filter(company=company)
    prepaid = get_object_or_404(qs, pk=pk)

    return render(request, 'bookkeeping/prepaid_expense_detail.html', {
        'prepaid': prepaid,
        'amortization_logs': prepaid.amortization_logs.order_by('-period_end'),
        'currency_symbol': RUPEE,
    })


@_login_required
def prepaid_expense_post_amortization(request, pk):
    from ..models import PrepaidExpense
    from ..prepaid_expense_service import post_prepaid_amortization

    company = request.user_company
    qs = PrepaidExpense.objects.filter(is_deleted=False)
    if not request.user.is_superuser and company:
        qs = qs.filter(company=company)
    prepaid = get_object_or_404(qs, pk=pk)

    if request.method == 'POST':
        period_start_str = request.POST.get('period_start', '').strip()
        period_end_str = request.POST.get('period_end', '').strip()
        period_start = _parse_ad_date(period_start_str)
        period_end = _parse_ad_date(period_end_str)
        if not period_start or not period_end:
            messages.error(request, "Enter a valid period start and end date.")
            return redirect('bookkeeping:prepaid_expense_detail', pk=pk)

        try:
            post_prepaid_amortization(prepaid, period_start, period_end, posted_by=request.user)
            messages.success(request, f"Amortization posted for {prepaid.name} ({period_start} to {period_end}).")
        except ValueError as exc:
            messages.error(request, str(exc))

        return redirect('bookkeeping:prepaid_expense_detail', pk=pk)

    return redirect('bookkeeping:prepaid_expense_detail', pk=pk)
