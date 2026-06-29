from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.http import require_http_methods
from ..forms import CustomerForm
from ..models import Customer
from ...utils.decorator import auth_required

@auth_required('customers.add_customer')
def create_customer(request):
    user = request.user
    user_company = user.company if not user.is_superuser else None

    if request.method == 'POST':
        form = CustomerForm(request.POST, user=user)
        if form.is_valid():
            customer = form.save(commit=False)
            if not user.is_superuser:
                customer.company = user_company
                customer.created_by = user
            customer.save()
            
            # Handle opening balance if provided
            opening_balance_amount = form.cleaned_data.get('opening_balance_amount')
            opening_balance_type = form.cleaned_data.get('opening_balance_type')
            
            if opening_balance_amount and opening_balance_amount > 0:
                try:
                    customer.update_opening_balance(
                        amount=opening_balance_amount,
                        opening_type=opening_balance_type
                    )
                    messages.success(request, f'Customer created successfully with opening balance of {opening_balance_amount}.')
                except Exception as e:
                    messages.warning(request, f'Customer created but failed to set opening balance: {str(e)}')
            else:
                messages.success(request, 'Customer created successfully.')
            
            return redirect('customers:customer_dashboard')
        else:
            messages.error(request, 'Please correct the errors in the form.')
    else:
        form = CustomerForm(user=user)

    return render(request, 'customers/customer_form.html', {'form': form, 'title': 'Create Customer'})


@auth_required('customers.add_customer')
@require_http_methods(["GET", "POST"])
def customer_quick_create(request):
    """HTMX endpoint: GET returns modal form HTML; POST saves and returns JSON."""
    user = request.user
    user_company = user.company if not user.is_superuser else None

    if request.method == 'POST':
        form = CustomerForm(request.POST, user=user)
        if form.is_valid():
            customer = form.save(commit=False)
            if not user.is_superuser:
                customer.company = user_company
                customer.created_by = user
            customer.save()

            opening_balance_amount = form.cleaned_data.get('opening_balance_amount')
            opening_balance_type = form.cleaned_data.get('opening_balance_type')
            if opening_balance_amount and opening_balance_amount > 0:
                try:
                    customer.update_opening_balance(
                        amount=opening_balance_amount,
                        opening_type=opening_balance_type,
                    )
                except Exception:
                    pass

            import json
            response = HttpResponse(status=200)
            response['HX-Reswap'] = 'none'
            response['HX-Trigger'] = json.dumps({
                'customerCreated': {'id': str(customer.id), 'name': customer.name}
            })
            return response

        return render(request, 'customers/partials/quick_create_modal.html', {'form': form}, status=422)

    form = CustomerForm(user=user)
    return render(request, 'customers/partials/quick_create_modal.html', {'form': form})
