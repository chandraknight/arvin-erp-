from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from ..forms import BankAccountForm
from ..models import BankAccount


@login_required
def bank_account_list(request):
    company = getattr(request.user, 'company', None)
    accounts = BankAccount.active_objects.filter(company=company).select_related('ledger_account').order_by('bank_name') if company else BankAccount.active_objects.none()
    return render(request, 'payments/bank_accounts/bank_account_list.html', {
        'accounts': accounts,
    })


@login_required
def bank_account_create(request):
    company = getattr(request.user, 'company', None)
    if request.method == 'POST':
        form = BankAccountForm(request.POST)
        if form.is_valid():
            if not company:
                messages.error(request, "Your account is not associated with a company.")
            else:
                account = form.save(commit=False)
                account.company = company
                account.created_by = request.user
                account.save()
                messages.success(request, f"Bank account '{account.bank_name} — {account.account_number}' added.")
                return redirect('payments:bank_account_list')
    else:
        form = BankAccountForm()
    return render(request, 'payments/bank_accounts/bank_account_form.html', {'form': form, 'is_edit': False})


@login_required
def bank_account_update(request, pk):
    company = getattr(request.user, 'company', None)
    account = get_object_or_404(BankAccount, pk=pk, company=company)
    if request.method == 'POST':
        form = BankAccountForm(request.POST, instance=account)
        if form.is_valid():
            account = form.save(commit=False)
            account.updated_by = request.user
            account.save()
            messages.success(request, f"Bank account '{account.bank_name} — {account.account_number}' updated.")
            return redirect('payments:bank_account_list')
    else:
        form = BankAccountForm(instance=account)
    return render(request, 'payments/bank_accounts/bank_account_form.html', {'form': form, 'is_edit': True, 'account': account})
