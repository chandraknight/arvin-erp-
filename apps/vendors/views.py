import json
from django.contrib import messages
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import redirect, render
from apps.vendors.forms import VendorForm
from apps.utils.decorator import auth_required
from apps.utils.htmx import is_htmx, toast_trigger
from apps.vendors.models import Vendor


def _post_opening_balance_journal(vendor, amount, opening_type):
    """
    Create a double-entry journal for a vendor opening balance.

    Opening payable (CREDIT type — we owe vendor):
        DR  Opening Balance Equity
        CR  Accounts Payable – {Vendor}

    Opening receivable (DEBIT type — vendor owes us):
        DR  Accounts Payable – {Vendor}
        CR  Opening Balance Equity
    """
    from apps.bookkeeping.models import LedgerAccount, JournalEntry, JournalEntryLine
    from apps.company.services.company_services import setup_default_ledger_accounts
    from decimal import Decimal

    amount = Decimal(str(amount))
    if amount <= 0:
        return

    company = vendor.company
    setup_default_ledger_accounts(company)

    equity_account, _ = LedgerAccount.objects.get_or_create(
        company=company,
        name='Opening Balance Equity',
        defaults={'account_type': 'EQUITY'}
    )
    vendor_account = vendor.related_ledger_account
    if not vendor_account:
        return

    entry = JournalEntry.objects.create(
        company=company,
        date=__import__('django.utils.timezone', fromlist=['timezone']).now().date(),
        description=f'Opening Balance – {vendor.name}',
    )

    if opening_type == 'CREDIT':
        # We owe vendor → increase payable
        debit_account, credit_account = equity_account, vendor_account
    else:
        # Vendor owes us → reverse
        debit_account, credit_account = vendor_account, equity_account

    JournalEntryLine.objects.bulk_create([
        JournalEntryLine(journal_entry=entry, account=debit_account, entry_type='DEBIT', amount=amount),
        JournalEntryLine(journal_entry=entry, account=credit_account, entry_type='CREDIT', amount=amount),
    ])

@auth_required('vendors.add_vendor')
def vendor_create(request):
    if request.method == 'POST':
        form = VendorForm(request.POST, user=request.user)
        if form.is_valid():
            try:
                vendor = form.save(commit=False)
                if request.user.is_authenticated:
                    vendor.created_by = request.user
                    vendor.company = request.user.company
                vendor.save()
                
                # Handle opening balance if provided
                opening_balance_amount = form.cleaned_data.get('opening_balance_amount')
                opening_balance_type = form.cleaned_data.get('opening_balance_type')
                
                if opening_balance_amount and opening_balance_amount > 0:
                    try:
                        vendor.update_opening_balance(
                            amount=opening_balance_amount,
                            opening_type=opening_balance_type
                        )
                        _post_opening_balance_journal(vendor, opening_balance_amount, opening_balance_type)
                        messages.success(request, f'Vendor created with opening balance of {opening_balance_amount}.')
                    except Exception as e:
                        messages.warning(request, f'Vendor created but failed to set opening balance: {str(e)}')
                else:
                    messages.success(request, "Vendor created successfully.")
                
                return redirect('vendors:vendor_dashboard')
            except Exception as e:
                messages.error(request, f"An error occurred while creating the vendor: {e}")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = VendorForm(user=request.user)
    return render(request, 'vendors/vendor_form.html', {'form': form})


@auth_required('vendors.view_vendor')
def vendor_dashboard(request):
    from django.db.models import Q
    from apps.utils.htmx import is_htmx

    user_company = request.user.company
    vendors = Vendor.active_objects.filter(company=user_company).order_by('-created_at')

    # Live search
    q = request.GET.get('q', '').strip()
    if q:
        vendors = vendors.filter(
            Q(name__icontains=q) |
            Q(email__icontains=q) |
            Q(phone__icontains=q) |
            Q(contact_person__icontains=q)
        )

    try:
        paginate_by = int(request.GET.get('paginate_by', 20))
    except (ValueError, TypeError):
        paginate_by = 20

    paginator = Paginator(vendors, paginate_by)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    all_vendors = Vendor.active_objects.filter(company=user_company)
    vendors_with_email = all_vendors.exclude(email__exact='').count()
    vendors_with_phone = all_vendors.exclude(phone__exact='').count()
    total_vendors = all_vendors.count()

    context = {
        'page_obj': page_obj,
        'paginate_by': paginate_by,
        'object_list': page_obj.object_list,
        'total_vendors': total_vendors,
        'vendors_with_email': vendors_with_email,
        'vendors_with_phone': vendors_with_phone,
        'q': q,
    }

    if is_htmx(request):
        return render(request, 'vendors/partials/vendor_table.html', context)

    return render(request, 'vendors/vendor_dashboard.html', context)


@auth_required('vendors.change_vendor')
def vendor_update(request, pk):
    vendor = Vendor.active_objects.get(pk=pk, company=request.user.company)

    if request.method == 'POST':
        form = VendorForm(request.POST, instance=vendor, user=request.user)
        if form.is_valid():
            try:
                vendor = form.save(commit=False)
                vendor.updated_by = request.user
                vendor.save()
                
                # Handle opening balance if provided
                opening_balance_amount = form.cleaned_data.get('opening_balance_amount')
                opening_balance_type = form.cleaned_data.get('opening_balance_type')
                
                if opening_balance_amount is not None:
                    try:
                        vendor.update_opening_balance(
                            amount=opening_balance_amount,
                            opening_type=opening_balance_type
                        )
                        if opening_balance_amount > 0:
                            _post_opening_balance_journal(vendor, opening_balance_amount, opening_balance_type)
                        messages.success(request, f'Vendor updated with opening balance of {opening_balance_amount}.')
                    except Exception as e:
                        messages.warning(request, f'Vendor updated but failed to update opening balance: {str(e)}')
                else:
                    messages.success(request, "Vendor updated successfully.")
                
                return redirect('vendors:vendor_dashboard')
            except Exception as e:
                messages.error(request, f"An error occurred while updating the vendor: {e}")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        # Pre-populate form with existing opening balance
        initial_data = {}
        opening_balance = vendor.get_opening_balance()
        if opening_balance:
            initial_data['opening_balance_amount'] = opening_balance.amount
            initial_data['opening_balance_type'] = opening_balance.opening_type
        
        form = VendorForm(instance=vendor, initial=initial_data, user=request.user)
    
    return render(request, 'vendors/vendor_form.html', {
        'form': form, 
        'vendor': vendor,
        'title': 'Update Vendor',
        'is_update': True
    })


@auth_required('vendors.delete_vendor')
def vendor_delete(request, pk):
    vendor = Vendor.active_objects.get(pk=pk, company=request.user.company)

    if request.method == 'POST':
        try:
            vendor_name = vendor.name
            vendor.soft_delete(deleted_by=request.user)
            if is_htmx(request):
                response = HttpResponse(status=200, content='')
                response['HX-Trigger'] = json.dumps(
                    toast_trigger('success', f'Vendor "{vendor_name}" deleted.')
                )
                return response
            messages.success(request, f'Vendor "{vendor_name}" deleted successfully.')
            return redirect('vendors:vendor_dashboard')
        except Exception as e:
            if is_htmx(request):
                response = HttpResponse(status=500)
                response['HX-Trigger'] = json.dumps(
                    toast_trigger('error', f'Error deleting vendor: {e}')
                )
                return response
            messages.error(request, f"An error occurred while deleting the vendor: {e}")
            return redirect('vendors:vendor_dashboard')

    return render(request, 'vendors/vendor_confirm_delete.html', {
        'vendor': vendor,
        'title': 'Delete Vendor'
    })


def vendor_quick_create(request):
    """HTMX endpoint: GET returns modal form; POST saves and fires HX-Trigger."""
    from django.http import HttpResponse as HR
    import json as _json
    user = request.user
    company = user.company if not user.is_superuser else None

    if request.method == 'POST':
        form = VendorForm(request.POST)
        if form.is_valid():
            vendor = form.save(commit=False)
            if company:
                vendor.company = company
                vendor.created_by = user
            vendor.save()
            resp = HR(status=200)
            resp['HX-Reswap'] = 'none'
            resp['HX-Trigger'] = _json.dumps({
                'vendorCreated': {'id': str(vendor.id), 'name': vendor.name}
            })
            return resp
        from django.shortcuts import render as _render
        return _render(request, 'vendors/partials/quick_create_modal.html', {'form': form}, status=422)

    form = VendorForm()
    from django.shortcuts import render as _render
    return _render(request, 'vendors/partials/quick_create_modal.html', {'form': form})


@auth_required('vendors.view_vendor')
def vendor_json(request, pk):
    from django.http import JsonResponse
    vendor = Vendor.objects.filter(pk=pk, company=request.user.company).first()
    if not vendor:
        return JsonResponse({}, status=404)
    return JsonResponse({
        'name': vendor.name,
        'contact_person': vendor.contact_person or '',
        'email': vendor.email or '',
        'phone': vendor.phone or '',
        'pan_number': vendor.pan_number or '',
        'address': vendor.address or '',
        'vat_registered': vendor.vat_registered,
    })


@auth_required('vendors.view_vendor')
def vendor_detail(request, pk):
    vendor = Vendor.active_objects.get(pk=pk, company=request.user.company)
    opening_balance = vendor.get_opening_balance()
    
    context = {
        'vendor': vendor,
        'opening_balance': opening_balance,
        'title': 'Vendor Details'
    }
    return render(request, 'vendors/vendor_detail.html', context)
