import json
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404

from ..models import Customer
from ...utils.decorator import auth_required
from ...utils.htmx import is_htmx, toast_trigger


@auth_required('customers.change_customer')
def delete_customer(request, id):
    customer = get_object_or_404(Customer, pk=id)
    user_company = request.user.company
    if not user_company or customer.company != user_company:
        if is_htmx(request):
            response = HttpResponse(status=403)
            response['HX-Trigger'] = json.dumps(
                toast_trigger('error', "Unauthorized: customer doesn't belong to your company.")
            )
            return response
        messages.error(request, "Unauthorized action: Customer doesn't belong to your company.")
        return redirect('customers:customer_dashboard')

    if request.method == 'POST':
        try:
            name = customer.name
            customer.soft_delete(request.user)
            if is_htmx(request):
                response = HttpResponse(status=200, content='')
                response['HX-Trigger'] = json.dumps(
                    toast_trigger('success', f'Customer "{name}" deleted.')
                )
                return response
            messages.success(request, f'Customer "{name}" was successfully deleted.')
            return redirect('customers:customer_dashboard')
        except Exception as e:
            if is_htmx(request):
                response = HttpResponse(status=500)
                response['HX-Trigger'] = json.dumps(
                    toast_trigger('error', f'Error deleting customer: {e}')
                )
                return response
            messages.error(request, f'Error deleting customer: {str(e)}')
            return redirect('customers:customer_dashboard')

    context = {
        'customer': customer,
        'title': 'Confirm Customer Deletion',
        'message': f'Are you sure you want to delete {customer.name}?',
        'back_url': 'customers:customer_dashboard',
    }
    return render(request, 'customers/customer_confirm_delete.html', context)
