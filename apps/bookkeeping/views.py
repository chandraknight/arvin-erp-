from django.views.generic import ListView, View, UpdateView
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.urls import reverse_lazy
from django.db.models import Q, Sum, Case, When, Value, DecimalField
from django.utils import timezone
from datetime import datetime, date
from decimal import Decimal
from .models import JournalEntry, LedgerAccount, JournalEntryLine, LedgerOpeningBalance
from ..utils.constant import RUPEE
from ..utils.mixins import AuthMixin
from ..utils.nepali_date import bs_str_to_ad, ad_date_to_bs_str
from .view_collections.all_views import *


class JournalEntryListView(AuthMixin, ListView):
    model = JournalEntry
    template_name = 'bookkeeping/journal_entry_list.html'
    context_object_name = 'journal_entries'
    paginate_by = 20
    permission_required = ['bookkeeping.view_journalentry']

    def get_paginate_by(self, queryset):
        try:
            return int(self.request.GET.get('paginate_by', self.paginate_by))
        except (ValueError, TypeError):
            return self.paginate_by

    def get_queryset(self):
        from django.db.models import Q
        qs = super().get_queryset()
        if self.request.user_company:
            qs = qs.filter(company=self.request.user_company)
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(description__icontains=q)
        return qs.select_related('company').prefetch_related('lines__account').order_by('-date', '-created_at')

    def get_template_names(self):
        from apps.utils.htmx import is_htmx
        if is_htmx(self.request):
            return ['bookkeeping/partials/journal_entry_table.html']
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['currency_symbol'] = RUPEE
        context['paginate_by'] = self.get_paginate_by(self.get_queryset())
        context['q'] = self.request.GET.get('q', '')
        return context

class JournalEntryPdfView(AuthMixin, View):
    permission_required = ['bookkeeping.view_journalentry']

    def get(self, request, pk):
        from django.http import HttpResponse
        from django.template.loader import render_to_string
        from xhtml2pdf import pisa

        qs = JournalEntry.objects.prefetch_related('lines__account').select_related('company')
        if not request.user.is_superuser and request.user_company:
            qs = qs.filter(company=request.user_company)
        entry = get_object_or_404(qs, pk=pk)

        html = render_to_string('bookkeeping/journal_entry_pdf.html', {
            'entry': entry,
            'company': entry.company,
            'request': request,
        })
        response = HttpResponse(content_type='application/pdf')
        if request.GET.get('print'):
            response['Content-Disposition'] = f'inline; filename=journal_{entry.date}_{entry.pk}.pdf'
        else:
            response['Content-Disposition'] = f'attachment; filename=journal_{entry.date}_{entry.pk}.pdf'
        pisa.CreatePDF(html, dest=response, encoding='UTF-8')
        return response


class JournalEntryDetailView(AuthMixin, View):
    permission_required = ['bookkeeping.view_journalentry']

    def get(self, request, pk):
        qs = JournalEntry.objects.prefetch_related('lines__account')
        if not request.user.is_superuser and request.user_company:
            qs = qs.filter(company=request.user_company)
        entry = get_object_or_404(qs, pk=pk)
        return render(request, 'bookkeeping/journal_entry_detail.html', {'entry': entry})


class JournalEntryReverseView(AuthMixin, View):
    """POST-only — creates a mirror reversal entry and marks original as reversed."""
    permission_required = ['bookkeeping.change_journalentry']

    def post(self, request, pk):
        qs = JournalEntry.objects.filter(is_deleted=False)
        if not request.user.is_superuser and request.user_company:
            qs = qs.filter(company=request.user_company)
        entry = get_object_or_404(qs, pk=pk)

        if entry.is_reversed:
            messages.error(request, f"Journal entry is already reversed.")
            return redirect('bookkeeping:journal_entry_detail', pk=pk)

        reason = request.POST.get('reason', '').strip() or 'Manual reversal'
        from .models import reverse_journal
        reversal = reverse_journal(entry, reason=reason, user=request.user)
        messages.success(
            request,
            f"Reversal entry created — original marked as reversed. "
            f"Reversal ID: {str(reversal.pk)[:8]}…"
        )
        return redirect('bookkeeping:journal_entry_detail', pk=reversal.pk)


class LedgerAccountUpdateView(AuthMixin, UpdateView):
    model = LedgerAccount
    template_name = 'bookkeeping/ledger_account_form.html'
    permission_required = ['bookkeeping.change_ledgeraccount']
    success_url = reverse_lazy('bookkeeping:ledger_account_list')

    def get_queryset(self):
        return LedgerAccount.objects.filter(
            company=self.request.user_company, is_deleted=False
        )

    def get_form_class(self):
        from .forms import LedgerAccountForm
        return LedgerAccountForm

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw['company'] = self.request.user_company
        return kw

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        messages.success(self.request, f"Ledger account '{self.object.name}' updated.")
        return super().form_valid(form)


class LedgerAccountListView(AuthMixin, ListView):
    model = LedgerAccount
    template_name = 'bookkeeping/ledger_account_list.html'
    context_object_name = 'accounts'
    paginate_by = 20
    permission_required = ['bookkeeping.view_ledgeraccount']

    def get_paginate_by(self, queryset):
        try:
            return int(self.request.GET.get('paginate_by', self.paginate_by))
        except (ValueError, TypeError):
            return self.paginate_by

    def get_queryset(self):
        from django.db.models import Q
        qs = super().get_queryset()
        if self.request.user_company:
            qs = qs.filter(company=self.request.user_company)
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(code__icontains=q))
        account_type = self.request.GET.get('account_type', '').strip()
        if account_type:
            qs = qs.filter(account_type=account_type)
        return qs.select_related('parent_account').order_by('account_type', 'code', 'name')

    def get_template_names(self):
        from apps.utils.htmx import is_htmx
        if is_htmx(self.request):
            return ['bookkeeping/partials/ledger_account_table.html']
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['currency_symbol'] = RUPEE
        context['paginate_by'] = self.get_paginate_by(self.get_queryset())
        context['q'] = self.request.GET.get('q', '')
        context['account_type'] = self.request.GET.get('account_type', '')
        return context


class LedgerReportView(AuthMixin, View):
    template_name = 'bookkeeping/ledger_report.html'
    permission_required = ['bookkeeping.view_ledgeraccount']
    
    def get(self, request, account_id):
        account = get_object_or_404(LedgerAccount, id=account_id, company=request.user_company)
        
        # Get date filters from request
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        
        # Set default dates if not provided
        if not start_date:
            # Get current fiscal year start date or use current year start
            from apps.company.models import FiscalYear
            active_fiscal_year = FiscalYear.objects.filter(
                company=request.user_company,
                is_active=True
            ).first()
            if active_fiscal_year:
                start_date = active_fiscal_year.start_date
            else:
                start_date = date(date.today().year, 1, 1)
        else:
            start_date = bs_str_to_ad(start_date) or date(date.today().year, 1, 1)
            
        if not end_date:
            end_date = date.today()
        else:
            end_date = bs_str_to_ad(end_date) or date.today()
        
        # Get opening balance
        opening_balance = self.get_opening_balance(account, start_date)
        
        # Get transactions for the period
        transactions = self.get_transactions(account, start_date, end_date)
        
        # Calculate running balance
        running_balance = opening_balance['amount']
        transaction_data = []
        
        for transaction in transactions:
            if transaction['entry_type'] == 'DEBIT':
                if account.account_type in ['ASSET', 'EXPENSE']:
                    running_balance += transaction['amount']
                else:
                    running_balance -= transaction['amount']
            else:  # CREDIT
                if account.account_type in ['ASSET', 'EXPENSE']:
                    running_balance -= transaction['amount']
                else:
                    running_balance += transaction['amount']
            
            transaction_data.append({
                'date': transaction['date'],
                'date_bs': ad_date_to_bs_str(transaction['date']),
                'description': transaction['description'],
                'narration': transaction['narration'],
                'reference': transaction['reference'],
                'debit': transaction['amount'] if transaction['entry_type'] == 'DEBIT' else None,
                'credit': transaction['amount'] if transaction['entry_type'] == 'CREDIT' else None,
                'balance': running_balance
            })
        
        # Calculate period totals
        period_debits = sum(t['debit'] for t in transaction_data if t['debit'])
        period_credits = sum(t['credit'] for t in transaction_data if t['credit'])
        
        from apps.company.models import FiscalYear
        active_fy = FiscalYear.objects.filter(
            company=request.user_company, is_active=True
        ).first()
        existing_opening_balance = None
        if active_fy:
            existing_opening_balance = LedgerOpeningBalance.objects.filter(
                account=account, fiscal_year=active_fy
            ).first()

        context = {
            'account': account,
            'start_date': start_date,
            'end_date': end_date,
            'start_date_bs': ad_date_to_bs_str(start_date),
            'end_date_bs': ad_date_to_bs_str(end_date),
            'opening_balance': opening_balance,
            'transactions': transaction_data,
            'closing_balance': running_balance,
            'period_debits': period_debits,
            'period_credits': period_credits,
            'currency_symbol': RUPEE,
            'is_print': request.GET.get('print', False),
            'existing_opening_balance': existing_opening_balance,
        }
        
        return render(request, self.template_name, context)

    def post(self, request, account_id):
        """HTMX POST — set opening balance and create journal entry."""
        from django.contrib import messages
        from django.shortcuts import redirect
        from apps.company.models import FiscalYear

        account = get_object_or_404(LedgerAccount, id=account_id, company=request.user_company)

        try:
            amount = Decimal(request.POST.get('amount', '0') or '0')
        except Exception:
            amount = Decimal('0')

        opening_type = request.POST.get('opening_type', 'DEBIT')
        date_str = request.POST.get('date', '').strip()

        active_fy = FiscalYear.objects.filter(
            company=request.user_company, is_active=True
        ).first()

        if not active_fy:
            messages.error(request, "No active fiscal year found.")
            return redirect('bookkeeping:ledger_report', account_id=account_id)

        if amount <= 0:
            messages.error(request, "Amount must be greater than zero.")
            return redirect('bookkeeping:ledger_report', account_id=account_id)

        # Save / update the opening balance record
        LedgerOpeningBalance.objects.update_or_create(
            account=account,
            fiscal_year=active_fy,
            defaults={'amount': amount, 'opening_type': opening_type},
        )

        # Resolve entry date
        entry_date = bs_str_to_ad(date_str) if date_str else active_fy.start_date

        # Find the contra account ("Opening Balance Equity" or similar)
        contra = (
            LedgerAccount.objects.filter(
                company=account.company,
                name__icontains='Opening Balance',
            )
            .exclude(pk=account.pk)
            .first()
        )

        if contra:
            journal = JournalEntry.objects.create(
                company=account.company,
                date=entry_date,
                description=f"Opening Balance – {account.name}",
            )
            counter_type = 'CREDIT' if opening_type == 'DEBIT' else 'DEBIT'
            JournalEntryLine.objects.bulk_create([
                JournalEntryLine(
                    journal_entry=journal,
                    account=account,
                    entry_type=opening_type,
                    amount=amount,
                    narration="Opening Balance",
                ),
                JournalEntryLine(
                    journal_entry=journal,
                    account=contra,
                    entry_type=counter_type,
                    amount=amount,
                    narration="Opening Balance",
                ),
            ])
            messages.success(
                request,
                f"Opening balance of {amount} ({opening_type}) set and journal entry created."
            )
        else:
            messages.warning(
                request,
                f"Opening balance saved, but no 'Opening Balance' contra account found — journal entry skipped."
            )

        return redirect('bookkeeping:ledger_report', account_id=account_id)

    def get_opening_balance(self, account, start_date):
        """Get opening balance for the account at the start date"""
        from apps.company.models import FiscalYear
        
        # Get active fiscal year
        active_fiscal_year = FiscalYear.objects.filter(
            company=account.company,
            is_active=True
        ).first()
        
        opening_balance = Decimal('0.00')
        opening_type = 'DEBIT' if account.account_type in ['ASSET', 'EXPENSE'] else 'CREDIT'
        
        if active_fiscal_year:
            # Get opening balance from LedgerOpeningBalance
            ledger_opening = LedgerOpeningBalance.objects.filter(
                account=account,
                fiscal_year=active_fiscal_year
            ).first()
            
            if ledger_opening:
                opening_balance = ledger_opening.amount
                opening_type = ledger_opening.opening_type
            
            # Add transactions from fiscal year start to report start date
            if start_date > active_fiscal_year.start_date:
                transactions_before = JournalEntryLine.objects.filter(
                    account=account,
                    journal_entry__date__gte=active_fiscal_year.start_date,
                    journal_entry__date__lt=start_date,
                    journal_entry__company=account.company,
                    journal_entry__is_reversed=False,
                    journal_entry__is_deleted=False,
                    is_deleted=False,
                ).select_related('journal_entry')
                
                for transaction in transactions_before:
                    if transaction.entry_type == 'DEBIT':
                        if account.account_type in ['ASSET', 'EXPENSE']:
                            opening_balance += transaction.amount
                        else:
                            opening_balance -= transaction.amount
                    else:  # CREDIT
                        if account.account_type in ['ASSET', 'EXPENSE']:
                            opening_balance -= transaction.amount
                        else:
                            opening_balance += transaction.amount
        
        return {
            'amount': opening_balance,
            'type': opening_type
        }
    
    def get_transactions(self, account, start_date, end_date):
        transactions = JournalEntryLine.objects.filter(
            account=account,
            journal_entry__date__gte=start_date,
            journal_entry__date__lte=end_date,
            journal_entry__company=account.company,
            journal_entry__is_reversed=False,
            journal_entry__is_deleted=False,
            is_deleted=False,
        ).select_related('journal_entry').order_by('journal_entry__date', 'journal_entry__id')
        
        transaction_data = []
        for transaction in transactions:
            transaction_data.append({
                'date': transaction.journal_entry.date,
                'description': transaction.journal_entry.description or '',
                'narration': transaction.narration or '',
                'reference': f"JE-{transaction.journal_entry.id}",
                'entry_type': transaction.entry_type,
                'amount': transaction.amount
            })
        
        return transaction_data


# ─────────────────────────────────────────────────────────────────────────────
# SUPERADMIN — Journal Audit Log
# Shows every JournalEntry (including reversed ones) with reversal chain.
# Only accessible to is_superuser.
# ─────────────────────────────────────────────────────────────────────────────
class JournalAuditLogView(AuthMixin, View):
    """
    Superadmin-only view: every journal entry ever created, including reversed
    ones. Lets auditors verify that no entries were deleted and that each
    reversal has a matching mirror entry.
    """
    permission_required = []  # guarded below with is_superuser check

    def get(self, request):
        from django.core.exceptions import PermissionDenied
        if not request.user.is_superuser:
            raise PermissionDenied

        from apps.activity_log.models import ActivityLog

        # All journal entries across all companies, oldest-first for audit trail
        qs = JournalEntry.objects.select_related(
            'company', 'reversal_of'
        ).prefetch_related('lines__account', 'reversals').order_by('-date', '-created_at')

        company_id = request.GET.get('company')
        if company_id:
            qs = qs.filter(company_id=company_id)

        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(description__icontains=q)

        show = request.GET.get('show', 'all')
        if show == 'reversed':
            qs = qs.filter(is_reversed=True)
        elif show == 'active':
            qs = qs.filter(is_reversed=False, is_deleted=False)

        # Reversal activity logs for sidebar panel
        reversal_logs = ActivityLog.objects.filter(
            action=ActivityLog.ACTION_REVERSE
        ).select_related('user').order_by('-timestamp')[:100]

        from django.core.paginator import Paginator
        paginator = Paginator(qs, 50)
        page = paginator.get_page(request.GET.get('page', 1))

        from apps.company.models import Company
        companies = Company.objects.filter(is_deleted=False).order_by('name')

        return render(request, 'bookkeeping/journal_audit_log.html', {
            'page_obj': page,
            'reversal_logs': reversal_logs,
            'companies': companies,
            'selected_company': company_id or '',
            'q': q,
            'show': show,
            'currency_symbol': RUPEE,
        })
