"""
ERP admin views for controlling the e-commerce storefront.
All views require staff login.
"""
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

from apps.products.models import Product, Category, ProductStock
from apps.ecom.models import EcomOrder, DiscountCoupon, SiteSettings
from apps.ecom.services import create_sales_order_from_ecom
from apps.company.models import Company


def _get_company(request):
    return request.user.profile.company if hasattr(request.user, 'profile') else Company.objects.first()


@login_required
def dashboard(request):
    from django.utils import timezone
    from django.db.models import Sum, Count
    from apps.products.models import Package, ProductStock

    company = _get_company(request)
    today = timezone.now().date()

    ecom_products_count = Product.objects.filter(company=company, show_on_ecom=True).count()
    pending_orders = EcomOrder.objects.filter(company=company, status='PENDING').count()
    today_orders = EcomOrder.objects.filter(company=company, created_at__date=today).count()
    dispatched_orders = EcomOrder.objects.filter(company=company, status='DISPATCHED').count()
    active_bundles = Package.objects.filter(company=company, show_on_ecom=True).count()

    revenue_data = EcomOrder.objects.filter(
        company=company, status__in=['DELIVERED', 'DISPATCHED', 'PROCESSING']
    ).aggregate(total=Sum('total'))
    total_revenue = revenue_data['total'] or 0

    recent_orders = EcomOrder.objects.filter(company=company).select_related('sales_order').order_by('-created_at')[:10]
    site = SiteSettings.objects.filter(company=company).first()

    # Low stock: ecom products with ecom_stock ≤ 5
    low_stock_products = (
        ProductStock.objects
        .filter(product__company=company, product__show_on_ecom=True, ecom_stock__lte=5, ecom_stock__gt=0)
        .select_related('product')
        .order_by('ecom_stock')[:8]
    )

    return render(request, 'ecom/admin/dashboard.html', {
        'ecom_products_count': ecom_products_count,
        'pending_orders': pending_orders,
        'today_orders': today_orders,
        'dispatched_orders': dispatched_orders,
        'active_bundles': active_bundles,
        'total_revenue': total_revenue,
        'recent_orders': recent_orders,
        'low_stock_products': low_stock_products,
        'site': site,
    })


@login_required
def product_list(request):
    from django.db.models import Q
    company = _get_company(request)
    categories = Category.objects.filter(company=company).only('id', 'name').order_by('name')
    category_id = request.GET.get('category')
    search = request.GET.get('q', '').strip()

    qs = (
        Product.objects
        .filter(company=company)
        .select_related('category')
        .prefetch_related('images')
        .only('id', 'name', 'price', 'show_on_ecom', 'category__name')
        .order_by('name')
    )
    if category_id:
        qs = qs.filter(category_id=category_id)
    if search:
        qs = qs.filter(Q(name__icontains=search) | Q(barcode__icontains=search) | Q(sku__icontains=search))

    paginator = Paginator(qs, 50)
    try:
        page_obj = paginator.page(request.GET.get('page', 1))
    except (EmptyPage, PageNotAnInteger):
        page_obj = paginator.page(1)

    return render(request, 'ecom/admin/product_list.html', {
        'products': page_obj,
        'page_obj': page_obj,
        'categories': categories,
        'selected_category': category_id,
        'search': search,
    })


@login_required
@require_POST
def toggle_product_ecom(request, product_id):
    company = _get_company(request)
    product = get_object_or_404(Product, id=product_id, company=company)
    product.show_on_ecom = not product.show_on_ecom
    product.save(update_fields=['show_on_ecom'])

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'show_on_ecom': product.show_on_ecom, 'ok': True})

    state = 'shown on' if product.show_on_ecom else 'hidden from'
    messages.success(request, f'{product.name} is now {state} the ecom site.')
    return redirect('ecom:admin_product_list')


@login_required
@require_POST
def bulk_toggle_ecom(request):
    """Enable or disable ecom for multiple products at once."""
    company = _get_company(request)
    product_ids = request.POST.getlist('product_ids')
    action = request.POST.get('action')  # 'enable' or 'disable'

    if action not in ('enable', 'disable'):
        messages.error(request, 'Invalid action.')
        return redirect('ecom:admin_product_list')

    show = action == 'enable'
    count = Product.objects.filter(id__in=product_ids, company=company).update(show_on_ecom=show)
    messages.success(request, f'{count} product(s) {"enabled on" if show else "hidden from"} ecom.')
    return redirect('ecom:admin_product_list')


@login_required
def order_list(request):
    company = _get_company(request)
    status = request.GET.get('status', '')
    orders = EcomOrder.objects.filter(company=company).select_related('sales_order', 'customer')
    if status:
        orders = orders.filter(status=status)

    return render(request, 'ecom/admin/order_list.html', {
        'orders': orders,
        'selected_status': status,
        'status_choices': EcomOrder._meta.get_field('status').choices,
    })


@login_required
def order_detail(request, order_id):
    company = _get_company(request)
    order = get_object_or_404(EcomOrder, id=order_id, company=company)
    return render(request, 'ecom/admin/order_detail.html', {'order': order})


@login_required
@require_POST
def order_create_sales_order(request, order_id):
    company = _get_company(request)
    order = get_object_or_404(EcomOrder, id=order_id, company=company)
    if order.sales_order_id:
        messages.info(request, 'Sales order already exists.')
    else:
        try:
            so = create_sales_order_from_ecom(order)
            messages.success(request, f'Sales order {so.order_number} created.')
        except Exception as e:
            messages.error(request, f'Failed to create sales order: {e}')
    return redirect('ecom:admin_order_detail', order_id=order_id)


@login_required
def order_print_slip(request, order_id):
    company = _get_company(request)
    order = get_object_or_404(EcomOrder, id=order_id, company=company)
    site = SiteSettings.objects.filter(company=company).first()
    mode = request.GET.get('mode', 'a4')  # 'a4' or 'thermal'
    return render(request, 'ecom/admin/order_print_slip.html', {
        'order': order,
        'site': site,
        'mode': mode,
    })


@login_required
@require_POST
def update_order_status(request, order_id):
    company = _get_company(request)
    order = get_object_or_404(EcomOrder, id=order_id, company=company)
    new_status = request.POST.get('status')
    valid = [s[0] for s in EcomOrder._meta.get_field('status').choices]
    if new_status not in valid:
        messages.error(request, 'Invalid status.')
        return redirect('ecom:admin_order_detail', order_id=order_id)

    order.status = new_status
    # When admin marks delivered, auto-collect COD
    if new_status == 'DELIVERED' and order.payment_method == 'COD' and order.cod_status == 'PENDING':
        order.cod_status = 'COLLECTED'
    order.save(update_fields=['status', 'cod_status'])

    # Mirror status to the linked SalesOrder
    if order.sales_order:
        status_map = {
            'PENDING':    'DRAFT',
            'CONFIRMED':  'CONFIRMED',
            'PROCESSING': 'PROCESSING',
            'DISPATCHED': 'DISPATCHED',
            'DELIVERED':  'DELIVERED',
            'CANCELLED':  'CANCELLED',
        }
        so_status = status_map.get(new_status)
        if so_status:
            order.sales_order.status = so_status
            order.sales_order.save(update_fields=['status'])

    messages.success(request, f'Order status updated to {order.get_status_display()}.')
    return redirect('ecom:admin_order_detail', order_id=order_id)


@login_required
@require_POST
def update_cod_status(request, order_id):
    company = _get_company(request)
    order = get_object_or_404(EcomOrder, id=order_id, company=company)
    new_cod = request.POST.get('cod_status')
    valid = [s[0] for s in EcomOrder._meta.get_field('cod_status').choices]
    if new_cod not in valid:
        messages.error(request, 'Invalid COD status.')
        return redirect('ecom:admin_order_detail', order_id=order_id)

    order.cod_status = new_cod
    # When cash is collected, auto-mark order as Delivered
    if new_cod == 'COLLECTED' and order.status not in ('DELIVERED', 'CANCELLED'):
        order.status = 'DELIVERED'
        if order.sales_order:
            order.sales_order.status = 'DELIVERED'
            order.sales_order.save(update_fields=['status'])
    order.save(update_fields=['cod_status', 'status'])
    messages.success(request, f'COD status updated to {order.get_cod_status_display()}.')
    return redirect('ecom:admin_order_detail', order_id=order_id)


@login_required
def category_image_list(request):
    company = _get_company(request)
    categories = Category.objects.filter(company=company).order_by('name')
    return render(request, 'ecom/admin/category_image_list.html', {'categories': categories})


@login_required
@require_POST
def update_category_image(request, category_id):
    company = _get_company(request)
    category = get_object_or_404(Category, id=category_id, company=company)
    if 'clear' in request.POST:
        if category.ecom_image:
            category.ecom_image.delete(save=False)
            category.ecom_image = None
            category.save(update_fields=['ecom_image'])
        messages.success(request, f'Image removed from "{category.name}".')
    elif 'ecom_image' in request.FILES:
        category.ecom_image = request.FILES['ecom_image']
        category.save(update_fields=['ecom_image'])
        messages.success(request, f'Image updated for "{category.name}".')
    return redirect('ecom:admin_category_images')


# ── Coupon management ─────────────────────────────────────────────────────────

@login_required
def coupon_list(request):
    company = _get_company(request)
    coupons = DiscountCoupon.objects.filter(company=company)
    return render(request, 'ecom/admin/coupon_list.html', {'coupons': coupons})


@login_required
def coupon_create(request):
    company = _get_company(request)
    if request.method == 'POST':
        code = request.POST.get('code', '').strip().upper()
        discount_type = request.POST.get('discount_type', 'PERCENT')
        value = request.POST.get('value', '0')
        min_order = request.POST.get('min_order_amount', '0') or '0'
        max_uses = request.POST.get('max_uses', '').strip() or None
        valid_from = request.POST.get('valid_from', '').strip() or None
        valid_until = request.POST.get('valid_until', '').strip() or None

        if not code:
            messages.error(request, 'Coupon code is required.')
            return redirect('ecom:coupon_list')

        if DiscountCoupon.objects.filter(company=company, code__iexact=code).exists():
            messages.error(request, f'Coupon code "{code}" already exists.')
            return redirect('ecom:coupon_list')

        DiscountCoupon.objects.create(
            company=company,
            code=code,
            discount_type=discount_type,
            value=value,
            min_order_amount=min_order,
            max_uses=max_uses,
            valid_from=valid_from,
            valid_until=valid_until,
        )
        messages.success(request, f'Coupon "{code}" created.')
        return redirect('ecom:coupon_list')

    ctx = {'discount_types': [('PERCENT', 'Percentage (%)'), ('FIXED', 'Fixed Amount (Rs.)')]}
    if request.GET.get('modal'):
        return render(request, 'ecom/admin/coupon_form_modal.html', ctx)
    return render(request, 'ecom/admin/coupon_form.html', ctx)


@login_required
@require_POST
def coupon_toggle(request, coupon_id):
    company = _get_company(request)
    coupon = get_object_or_404(DiscountCoupon, id=coupon_id, company=company)
    coupon.is_active = not coupon.is_active
    coupon.save(update_fields=['is_active'])
    state = 'activated' if coupon.is_active else 'deactivated'
    messages.success(request, f'Coupon "{coupon.code}" {state}.')
    return redirect('ecom:coupon_list')


@login_required
def ecom_inventory(request):
    company = _get_company(request)

    if request.method == 'POST':
        from apps.ecom.stock_services import bulk_set_ecom_prices, bulk_set_ecom_stock
        quantities = {}
        prices = {}
        for key, value in request.POST.items():
            if key.startswith('qty_') and value.strip() != '':
                try:
                    qty = int(value)
                except ValueError:
                    continue
                if qty >= 0:
                    quantities[key[4:]] = qty
            elif key.startswith('price_') and value.strip() != '':
                # Compare-at is paired with price: a row is repriced only when
                # a selling price is entered, so a blank compare clears the discount.
                pid = key[6:]
                prices[pid] = {
                    'price': value.strip(),
                    'compare_at_price': request.POST.get(f'compare_{pid}', '').strip(),
                }
        updated, skipped = bulk_set_ecom_stock(company, request.user, quantities)
        p_updated, p_skipped = bulk_set_ecom_prices(company, prices)
        updated += p_updated
        skipped += p_skipped
        if updated:
            messages.success(request, f'Updated {updated} product(s).')
        for name, reason in skipped:
            messages.error(request, f'{name}: {reason}')
        if not updated and not skipped:
            messages.info(request, 'No changes to save.')
        if not request.headers.get('HX-Request'):
            params = request.GET.urlencode()
            return redirect(f"{request.path}?{params}" if params else request.path)

    from django.db.models import Count, F, Q, Sum, Value
    from django.db.models.functions import Coalesce

    categories = Category.objects.filter(company=company).only('id', 'name').order_by('name')
    category_id = request.GET.get('category')
    search = request.GET.get('q', '').strip()

    base_qs = Product.objects.filter(company=company, show_on_ecom=True, is_service=False)
    stats = base_qs.aggregate(
        total=Count('id'),
        ecom_units=Sum('productstock__ecom_stock'),
        pos_units=Sum('productstock__stock'),
        out_of_stock=Count(
            'id', filter=Q(productstock__ecom_stock=0) | Q(productstock__isnull=True)
        ),
    )

    qs = (
        base_qs
        .select_related('category', 'productstock')
        .annotate(
            max_ecom=Coalesce(F('productstock__stock'), Value(0))
            + Coalesce(F('productstock__ecom_stock'), Value(0))
        )
        .order_by(F('productstock__ecom_stock').asc(nulls_first=True), 'name')
    )
    if category_id:
        qs = qs.filter(category_id=category_id)
    if search:
        qs = qs.filter(Q(name__icontains=search) | Q(barcode__icontains=search) | Q(sku__icontains=search))

    paginator = Paginator(qs, 50)
    try:
        page_obj = paginator.page(request.GET.get('page', 1))
    except (EmptyPage, PageNotAnInteger):
        page_obj = paginator.page(1)

    context = {
        'products': page_obj,
        'page_obj': page_obj,
        'categories': categories,
        'selected_category': category_id,
        'search': search,
        'stats': stats,
    }
    if request.headers.get('HX-Request'):
        return render(request, 'ecom/admin/_inventory_panel.html', context)
    return render(request, 'ecom/admin/inventory_list.html', context)


# ── Package management (ecom admin) ──────────────────────────────────────────

@login_required
def package_list(request):
    from apps.products.models import Package
    company = _get_company(request)
    packages = Package.objects.filter(company=company).prefetch_related('items__product').order_by('name')
    return render(request, 'ecom/admin/package_list.html', {'packages': packages, 'company': company})


@login_required
def package_create(request):
    from apps.products.models import Package, PackageItem
    company = _get_company(request)
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        price = request.POST.get('price', '0')
        compare_at_price = request.POST.get('compare_at_price', '').strip() or None
        show_on_ecom = request.POST.get('show_on_ecom') == 'on'
        ecom_description = request.POST.get('ecom_description', '').strip()
        ecom_image = request.FILES.get('ecom_image')
        if not name or not price:
            messages.error(request, 'Name and price are required.')
            return redirect('ecom:admin_package_list')
        pkg = Package.objects.create(
            company=company, name=name, price=price,
            compare_at_price=compare_at_price,
            show_on_ecom=show_on_ecom,
            ecom_description=ecom_description or None,
        )
        if ecom_image:
            pkg.ecom_image = ecom_image
            pkg.save(update_fields=['ecom_image'])
        product_ids = request.POST.getlist('product_ids')
        quantities = request.POST.getlist('quantities')
        for pid, qty in zip(product_ids, quantities):
            if pid and qty:
                from apps.products.models import Product as Prod
                try:
                    product = Prod.objects.get(id=pid, company=company)
                    PackageItem.objects.create(package=pkg, product=product, quantity=int(qty))
                except Exception:
                    pass
        messages.success(request, f'Package "{pkg.name}" created.')
        return redirect('ecom:admin_package_list')
    from apps.products.models import Product as Prod
    products = Prod.objects.filter(company=company, show_on_ecom=True).order_by('name')
    return render(request, 'ecom/admin/package_form.html', {'company': company, 'products': products, 'pkg': None})


@login_required
def package_edit(request, package_id):
    from apps.products.models import Package, PackageItem, Product as Prod
    company = _get_company(request)
    pkg = get_object_or_404(Package, id=package_id, company=company)
    if request.method == 'POST':
        pkg.name = request.POST.get('name', pkg.name).strip()
        pkg.price = request.POST.get('price', pkg.price)
        pkg.compare_at_price = request.POST.get('compare_at_price', '').strip() or None
        pkg.show_on_ecom = request.POST.get('show_on_ecom') == 'on'
        pkg.ecom_description = request.POST.get('ecom_description', '').strip() or None
        if request.FILES.get('ecom_image'):
            pkg.ecom_image = request.FILES['ecom_image']
        pkg.save()
        pkg.items.all().delete()
        product_ids = request.POST.getlist('product_ids')
        quantities = request.POST.getlist('quantities')
        for pid, qty in zip(product_ids, quantities):
            if pid and qty:
                try:
                    product = Prod.objects.get(id=pid, company=company)
                    PackageItem.objects.create(package=pkg, product=product, quantity=int(qty))
                except Exception:
                    pass
        messages.success(request, f'Package "{pkg.name}" updated.')
        return redirect('ecom:admin_package_list')
    products = Prod.objects.filter(company=company, show_on_ecom=True).order_by('name')
    return render(request, 'ecom/admin/package_form.html', {'company': company, 'products': products, 'pkg': pkg})


@login_required
@require_POST
def package_delete(request, package_id):
    from apps.products.models import Package
    company = _get_company(request)
    pkg = get_object_or_404(Package, id=package_id, company=company)
    name = pkg.name
    pkg.delete()
    messages.success(request, f'Package "{name}" deleted.')
    return redirect('ecom:admin_package_list')
