from django.db.models import Count, Q
from django.db.models.functions import TruncMonth
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from .services.all_services import *
from apps.vendors.models import Vendor


@auth_required('customers.view_customer')
def customer_json(request, pk):
    customer = Customer.objects.filter(pk=pk, company=request.user.company).first()
    if not customer:
        return JsonResponse({}, status=404)
    return JsonResponse({
        'name': customer.name,
        'email': customer.email or '',
        'phone': customer.phone or '',
        'pan_number': customer.pan_number or '',
        'address': customer.address or '',
    })


@auth_required('customers.view_customer')
def customer_dashboard(request):
    from django.db.models import Q
    from apps.utils.htmx import is_htmx

    if request.user.is_superuser:
        customers = Customer.active_objects.all().order_by('-created_at')
    else:
        customers = Customer.active_objects.filter(company=request.user.company).order_by('-created_at')

    # Live search
    q = request.GET.get('q', '').strip()
    if q:
        customers = customers.filter(
            Q(name__icontains=q) |
            Q(email__icontains=q) |
            Q(phone__icontains=q)
        )

    email_count = customers.exclude(email__isnull=True).exclude(email__exact='').count()
    phone_count = customers.exclude(phone__isnull=True).exclude(phone__exact='').count()

    try:
        paginate_by = int(request.GET.get('paginate_by', 20))
    except (ValueError, TypeError):
        paginate_by = 20

    paginator = Paginator(customers, paginate_by)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'object_list': page_obj.object_list,
        'page_obj': page_obj,
        'email_count': email_count,
        'phone_count': phone_count,
        'paginate_by': paginate_by,
        'q': q,
        'total_count': customers.count(),
    }

    if is_htmx(request):
        return render(request, 'customers/partials/customer_table.html', context)

    return render(request, 'customers/customer_dashboard.html', context)


@login_required
def customer_acquisition_report(request):
    user_company = request.user.company
    if not user_company:
        messages.warning(request, "Your account is not associated with a company. Please contact an administrator.")
        return redirect('accounts:user_dashboard')

    customers = Customer.active_objects.filter(company=user_company)

    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')

    if start_date:
        customers = customers.filter(created_at__gte=start_date)
    if end_date:
        customers = customers.filter(created_at__lte=end_date)

    monthly_acquisition_data = customers.annotate(
        month=TruncMonth('created_at')
    ).values('month').annotate(new_customers_count=Count('id')).order_by('month')

    acquisition_chart_labels = [data['month'].strftime('%Y-%m') for data in monthly_acquisition_data]
    acquisition_chart_data = [data['new_customers_count'] for data in monthly_acquisition_data]

    context = {
        'monthly_acquisition_data': monthly_acquisition_data,
        'acquisition_chart_labels': acquisition_chart_labels,
        'acquisition_chart_data': acquisition_chart_data,
        'selected_start_date': start_date,
        'selected_end_date': end_date,
    }

    return render(request, 'customers/customer_acquisition_report.html', context)


@auth_required('customers.view_customer')
def contacts_dashboard(request):
    from apps.utils.htmx import is_htmx

    tab = request.GET.get('tab', 'customers')
    q = request.GET.get('q', '').strip()

    try:
        paginate_by = int(request.GET.get('paginate_by', 20))
    except (ValueError, TypeError):
        paginate_by = 20

    # --- Customers ---
    if request.user.is_superuser:
        customers_qs = Customer.active_objects.all().order_by('-created_at')
    else:
        customers_qs = Customer.active_objects.filter(company=request.user.company).order_by('-created_at')

    if tab == 'customers' and q:
        customers_qs = customers_qs.filter(
            Q(name__icontains=q) | Q(email__icontains=q) | Q(phone__icontains=q)
        )

    customer_paginator = Paginator(customers_qs, paginate_by)
    customer_page = customer_paginator.get_page(request.GET.get('page', 1))

    # --- Vendors ---
    vendors_qs = Vendor.active_objects.filter(company=request.user.company).order_by('-created_at')

    if tab == 'vendors' and q:
        vendors_qs = vendors_qs.filter(
            Q(name__icontains=q) | Q(email__icontains=q) |
            Q(phone__icontains=q) | Q(contact_person__icontains=q)
        )

    vendor_paginator = Paginator(vendors_qs, paginate_by)
    vendor_page = vendor_paginator.get_page(request.GET.get('page', 1))

    from apps.pos.models import Referrer
    referrers = Referrer.objects.filter(company=request.user.company).order_by('name')

    context = {
        'tab': tab,
        'q': q,
        'paginate_by': paginate_by,
        'referrers': referrers,
        # customer context
        'customer_page_obj': customer_page,
        'customer_list': customer_page.object_list,
        'total_customers': customers_qs.count(),
        'customer_email_count': customers_qs.exclude(email__isnull=True).exclude(email__exact='').count(),
        'customer_phone_count': customers_qs.exclude(phone__isnull=True).exclude(phone__exact='').count(),
        # vendor context
        'vendor_page_obj': vendor_page,
        'vendor_list': vendor_page.object_list,
        'total_vendors': vendors_qs.count(),
        'vendor_email_count': vendors_qs.exclude(email__exact='').count(),
        'vendor_phone_count': vendors_qs.exclude(phone__exact='').count(),
    }

    if is_htmx(request):
        if tab == 'vendors':
            return render(request, 'customers/partials/contacts_vendor_table.html', context)
        return render(request, 'customers/partials/contacts_customer_table.html', context)

    return render(request, 'customers/contacts_dashboard.html', context)


@auth_required('customers.view_customer')
def referrer_list(request):
    from apps.pos.models import Referrer
    company = request.user.company
    referrers = Referrer.objects.filter(company=company).order_by('name')
    return render(request, 'customers/referrer_list.html', {'referrers': referrers})


@auth_required('customers.add_customer')
def referrer_create(request):
    from apps.pos.models import Referrer
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        phone = request.POST.get('phone', '').strip()
        if not name:
            messages.error(request, 'Name is required.')
        else:
            Referrer.objects.create(
                company=request.user.company,
                name=name,
                phone=phone,
                created_by=request.user,
            )
            messages.success(request, f'Referrer "{name}" added.')
        return redirect('customers:referrer_list')
    return redirect('customers:referrer_list')


@auth_required('customers.add_customer')
def referrer_update(request, pk):
    from apps.pos.models import Referrer
    referrer = get_object_or_404(Referrer, pk=pk, company=request.user.company)
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        phone = request.POST.get('phone', '').strip()
        if not name:
            messages.error(request, 'Name is required.')
        else:
            referrer.name = name
            referrer.phone = phone
            referrer.updated_by = request.user
            referrer.save()
            messages.success(request, f'Referrer "{name}" updated.')
    return redirect('customers:referrer_list')


@auth_required('customers.add_customer')
def referrer_delete(request, pk):
    from apps.pos.models import Referrer
    referrer = get_object_or_404(Referrer, pk=pk, company=request.user.company)
    if request.method == 'POST':
        referrer.delete()
        messages.success(request, 'Referrer deleted.')
    return redirect('customers:referrer_list')