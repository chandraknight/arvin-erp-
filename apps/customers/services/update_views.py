from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect
from ..forms import CustomerForm
from ..models import Customer
from django.shortcuts import get_object_or_404

from ...utils.decorator import auth_required

@auth_required('customers.change_customer')
def update_customer(request, id):
    customer = get_object_or_404(Customer, pk=id)

    if not request.user.is_superuser and customer.company != request.user.company:
        messages.error(request, "You do not have permission to edit this customer.")
        return redirect('customers:customer_dashboard')

    if request.method == 'POST':
        form = CustomerForm(request.POST, instance=customer, user=request.user)
        if form.is_valid():
            customer = form.save(commit=False)
            if not request.user.is_superuser:
                customer.company = request.user.company
            customer.save()
            messages.success(request, "Customer updated successfully.")
            return redirect('customers:customer_dashboard')
        else:
            messages.error(request, "Please correct the errors in the form.")
    else:
        form = CustomerForm(instance=customer, user=request.user)

    return render(request, 'customers/customer_form.html', {
        'form': form,
        'title': 'Update Customer',
    })
