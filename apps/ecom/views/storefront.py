"""
Public-facing e-commerce storefront views.
No login required — guests can browse and checkout.
"""
import json
from decimal import Decimal
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from django.db import transaction
from django.db.models import F

from apps.products.models import Product, Category, ProductStock, StockTransaction
from apps.company.models import Company
from apps.ecom.models import EcomOrder, EcomOrderItem, SiteSettings, HeroBanner, Page, Announcement, BlogPost, ContactMessage, DiscountCoupon
from apps.ecom.services import create_sales_order_from_ecom, validate_coupon, apply_coupon_to_order, notify_admin_new_order


def _get_company(request):
    return Company.objects.first()


def _require_ecom_enabled(company):
    from django.http import Http404
    if not company or not company.enable_ecom:
        raise Http404("E-Commerce store is not available.")


def _cms_context(company):
    """Common CMS data injected into every storefront page."""
    settings = SiteSettings.objects.filter(company=company).first()
    active_banners = HeroBanner.objects.filter(company=company, is_active=True)
    hero_banners = list(active_banners.filter(banner_type='HERO'))
    promo_banners = list(active_banners.filter(banner_type='PROMO'))
    # Right column of the 80/20 banner layout: use extra hero banners first, then promo banners
    # right column = PROMO type only; AD BANNERS section = PROMO type beyond slot 2
    right_banners = promo_banners[:2]
    display_promo_banners = promo_banners[2:]
    footer_pages = Page.objects.filter(company=company, is_published=True, show_in_footer=True)
    nav_pages = Page.objects.filter(company=company, is_published=True, show_in_nav=True)
    announcements = [a for a in Announcement.objects.filter(company=company) if a.is_visible()]
    top_banners = [a for a in announcements if a.announcement_type == 'BANNER']
    news = [a for a in announcements if a.announcement_type == 'NEWS']
    categories = Category.objects.filter(company=company).order_by('name')
    nav_categories = categories.filter(parent__isnull=True).prefetch_related('category_set')
    published_posts = BlogPost.objects.filter(company=company, is_published=True)
    return {
        'cms': settings,
        'hero_banners': hero_banners,
        'promo_banners': display_promo_banners,
        'right_banners': right_banners,
        'footer_pages': footer_pages,
        'top_announcements': top_banners,
        'news_items': news,
        'categories': categories,
        'nav_categories': nav_categories,
        'nav_pages': nav_pages,
        'has_blog': published_posts.exists(),
        'recent_blog_posts': published_posts[:3],
    }


# ──────────────────────────────────────────────────────────
# Cart helpers (session-based, no model required)
# ──────────────────────────────────────────────────────────

def _get_cart(request):
    return request.session.get('ecom_cart', {})


def _save_cart(request, cart):
    request.session['ecom_cart'] = cart
    request.session.modified = True


def _cart_totals(cart, products_map):
    subtotal = 0
    items = []
    for pid, qty in cart.items():
        product = products_map.get(pid)
        if product:
            line = float(product.price) * qty
            subtotal += line
            items.append({'product': product, 'quantity': qty, 'line_total': line})
    return items, subtotal


# ──────────────────────────────────────────────────────────
# Storefront views
# ──────────────────────────────────────────────────────────

def store_home(request):
    company = _get_company(request)
    _require_ecom_enabled(company)

    from django.utils import timezone as tz
    import datetime

    cutoff = tz.now() - datetime.timedelta(days=7)

    base_qs = Product.objects.filter(
        company=company, show_on_ecom=True
    ).select_related('category').prefetch_related('images', 'productstock')

    recent_qs = base_qs.filter(created_at__gte=cutoff).order_by('-created_at')

    flash_products = list(recent_qs[:12])
    if not flash_products:
        flash_products = list(base_qs.order_by('-created_at')[:12])

    new_arrivals = list(recent_qs[12:24])
    if not new_arrivals:
        new_arrivals = list(base_qs.order_by('-created_at')[12:24])

    total_product_count = base_qs.count()

    parent_categories = (
        Category.objects
        .filter(company=company, parent__isnull=True)
        .prefetch_related('category_set')
        .order_by('name')
    )

    from apps.products.models import Package
    popular_bundles = Package.objects.filter(company=company, show_on_ecom=True).prefetch_related('items__product')[:6]

    cart = _get_cart(request)
    ctx = _cms_context(company)
    ctx.update({
        'company': company,
        'flash_products': flash_products,
        'new_arrivals': new_arrivals,
        'parent_categories': parent_categories,
        'popular_bundles': popular_bundles,
        'total_product_count': total_product_count,
        'cart_count': sum(cart.values()),
    })
    return render(request, 'ecom/storefront/home.html', ctx)


def product_detail(request, product_id):
    company = _get_company(request)
    _require_ecom_enabled(company)
    product = get_object_or_404(
        Product.objects.prefetch_related('images', 'productstock'),
        id=product_id, company=company, show_on_ecom=True
    )
    related = Product.objects.filter(
        company=company, show_on_ecom=True, category=product.category
    ).exclude(id=product.id).prefetch_related('images', 'productstock')[:6]

    cart = _get_cart(request)
    ctx = _cms_context(company)
    ctx.update({
        'company': company,
        'product': product,
        'related_products': related,
        'cart_count': sum(cart.values()),
    })
    return render(request, 'ecom/storefront/product_detail.html', ctx)


@require_POST
def add_to_cart(request, product_id):
    company = _get_company(request)
    _require_ecom_enabled(company)
    product = get_object_or_404(Product, id=str(product_id), company=company, show_on_ecom=True)
    
    # Stock check for ecom_stock
    if hasattr(product, 'productstock'):
        if product.productstock.ecom_stock <= 0 and not product.is_service:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'error': 'Out of stock', 'ok': False}, status=400)
            messages.error(request, f"Sorry, {product.name} is currently out of stock.")
            return redirect('ecom:home')

    cart = _get_cart(request)
    pid = str(product_id)
    qty = int(request.POST.get('quantity', 1))
    
    # Check if total qty in cart exceeds available ecom_stock
    if hasattr(product, 'productstock') and not product.is_service:
        current_in_cart = cart.get(pid, 0)
        if current_in_cart + qty > product.productstock.ecom_stock:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'error': 'Insufficient stock', 'ok': False}, status=400)
            messages.error(request, f"Cannot add more of {product.name}. Only {product.productstock.ecom_stock} available.")
            return redirect('ecom:cart')

    cart[pid] = cart.get(pid, 0) + qty
    _save_cart(request, cart)

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'cart_count': sum(cart.values()), 'ok': True})
    return redirect('ecom:cart')


@require_POST
def remove_from_cart(request, product_id):
    cart = _get_cart(request)
    cart.pop(str(product_id), None)
    _save_cart(request, cart)
    return redirect('ecom:cart')


@require_POST
def update_cart(request, product_id):
    cart = _get_cart(request)
    pid = str(product_id)
    qty = int(request.POST.get('quantity', 1))
    if qty <= 0:
        cart.pop(pid, None)
    else:
        cart[pid] = qty
    _save_cart(request, cart)
    return redirect('ecom:cart')


@require_POST
def validate_coupon_view(request):
    company = _get_company(request)
    import json as _json
    try:
        body = _json.loads(request.body)
    except (ValueError, KeyError):
        body = {}
    code = body.get('code', request.POST.get('code', '')).strip()
    subtotal = body.get('subtotal', request.POST.get('subtotal', 0))
    result = validate_coupon(code, company, subtotal)
    return JsonResponse(result)


def cart_view(request):
    company = _get_company(request)
    _require_ecom_enabled(company)
    cart = _get_cart(request)
    products_map = {
        str(p.id): p
        for p in Product.objects.filter(id__in=cart.keys(), show_on_ecom=True).prefetch_related('images')
    }
    items, subtotal = _cart_totals(cart, products_map)
    site = SiteSettings.objects.filter(company=company).first()
    delivery_charge = Decimal('0.00')
    if site and site.delivery_charge > 0:
        threshold = site.free_shipping_threshold or 0
        if subtotal < threshold:
            delivery_charge = site.delivery_charge
    ctx = _cms_context(company)
    ctx.update({
        'company': company,
        'cart_items': items,
        'subtotal': subtotal,
        'delivery_charge': delivery_charge,
        'order_total': Decimal(str(subtotal)) + delivery_charge,
        'free_shipping_threshold': site.free_shipping_threshold if site else 5000,
        'cart_count': sum(cart.values()),
    })
    return render(request, 'ecom/storefront/cart.html', ctx)


def checkout(request):
    company = _get_company(request)
    _require_ecom_enabled(company)
    cart = _get_cart(request)

    if not cart:
        messages.warning(request, 'Your cart is empty.')
        return redirect('ecom:home')

    products_map = {
        str(p.id): p
        for p in Product.objects.filter(id__in=cart.keys(), show_on_ecom=True).prefetch_related('images')
    }
    items, subtotal = _cart_totals(cart, products_map)

    # Pre-fill from logged-in customer account
    initial = {}
    if request.user.is_authenticated and not request.user.is_staff:
        from apps.customers.models import Customer
        customer = Customer.objects.filter(company=company, email=request.user.email).first()
        if customer:
            initial = {
                'name': customer.name,
                'phone': customer.phone,
                'address': customer.address or '',
                'email': customer.email or '',
            }

    site = SiteSettings.objects.filter(company=company).first()
    delivery_charge = Decimal('0.00')
    if site and site.delivery_charge > 0:
        threshold = site.free_shipping_threshold or 0
        if subtotal < threshold:
            delivery_charge = site.delivery_charge
    order_total = Decimal(str(subtotal)) + delivery_charge

    ctx = _cms_context(company)
    ctx.update({
        'company': company,
        'cart_items': items,
        'subtotal': subtotal,
        'delivery_charge': delivery_charge,
        'order_total': order_total,
        'free_shipping_threshold': site.free_shipping_threshold if site else 5000,
        'cart_count': sum(cart.values()),
        'initial': initial,
    })
    return render(request, 'ecom/storefront/checkout.html', ctx)


@require_POST
@transaction.atomic
def place_order(request):
    company = _get_company(request)
    _require_ecom_enabled(company)
    cart = _get_cart(request)

    if not cart:
        messages.error(request, 'Your cart is empty.')
        return redirect('ecom:home')

    name = request.POST.get('name', '').strip()
    phone = request.POST.get('phone', '').strip()
    address = request.POST.get('delivery_address', '').strip()
    email = request.POST.get('email', '').strip() or None
    notes = request.POST.get('notes', '').strip() or None

    if not name or not phone or not address:
        messages.error(request, 'Name, phone, and delivery address are required.')
        return redirect('ecom:checkout')

    products_map = {
        str(p.id): p
        for p in Product.objects.filter(id__in=cart.keys(), show_on_ecom=True).select_related('productstock')
    }

    # Final stock check — lock rows to prevent race with concurrent checkouts
    stock_map = {
        str(s.product_id): s
        for s in ProductStock.objects.select_for_update().filter(
            product_id__in=cart.keys()
        )
    }
    for pid, qty in cart.items():
        product = products_map.get(pid)
        if product and not product.is_service:
            stock = stock_map.get(pid)
            if not stock or stock.ecom_stock < qty:
                messages.error(request, f"Sorry, {product.name} just went out of stock or has insufficient quantity.")
                return redirect('ecom:cart')

    ecom_order = EcomOrder(
        company=company,
        customer_name=name,
        customer_phone=phone,
        customer_email=email,
        delivery_address=address,
        notes=notes,
        payment_method='COD',
    )

    # Try to link logged-in customer
    if request.user.is_authenticated and not request.user.is_staff:
        from apps.customers.models import Customer
        customer = Customer.objects.filter(company=company, email=request.user.email).first()
        if customer:
            ecom_order.customer = customer

    # Compute totals before save
    subtotal = sum(float(products_map[pid].price) * qty for pid, qty in cart.items() if pid in products_map)
    ecom_order.subtotal = subtotal

    coupon_code = request.POST.get('coupon_code', '').strip()
    applied_coupon = None
    discount_amount = 0
    if coupon_code:
        result = validate_coupon(coupon_code, company, subtotal)
        if result['ok']:
            try:
                applied_coupon = DiscountCoupon.objects.get(code__iexact=coupon_code, company=company)
                discount_amount = result['discount']
            except DiscountCoupon.DoesNotExist:
                pass

    # Apply delivery charge (waived if subtotal meets free_shipping_threshold)
    site = SiteSettings.objects.filter(company=company).first()
    delivery_charge = Decimal('0.00')
    if site and site.delivery_charge > 0:
        threshold = site.free_shipping_threshold or 0
        if subtotal < threshold:
            delivery_charge = site.delivery_charge

    ecom_order.coupon = applied_coupon
    ecom_order.discount_amount = discount_amount
    ecom_order.delivery_charge = delivery_charge
    ecom_order.total = max(0, Decimal(str(subtotal)) - Decimal(str(discount_amount)) + delivery_charge)
    ecom_order.save()

    for pid, qty in cart.items():
        product = products_map.get(pid)
        if product:
            EcomOrderItem.objects.create(
                order=ecom_order,
                product=product,
                quantity=qty,
                unit_price=product.price,
            )
            # Deduct ecom stock
            if not product.is_service:
                ProductStock.objects.filter(product=product).update(
                    ecom_stock=F('ecom_stock') - qty
                )
                StockTransaction.objects.create(
                    product=product,
                    user=request.user if request.user.is_authenticated else None,
                    transaction_type='REMOVE',
                    stock_type='ECOM',
                    quantity=qty,
                    reason=f'Ecom order {ecom_order.order_number}',
                )

    if applied_coupon:
        apply_coupon_to_order(ecom_order, applied_coupon)

    create_sales_order_from_ecom(ecom_order)
    notify_admin_new_order(ecom_order)

    # Clear cart
    _save_cart(request, {})

    return redirect('ecom:order_success', order_number=ecom_order.order_number)


def order_success(request, order_number):
    company = _get_company(request)
    order = get_object_or_404(EcomOrder, order_number=order_number, company=company)
    ctx = _cms_context(company)
    ctx.update({'company': company, 'order': order, 'cart_count': 0})
    return render(request, 'ecom/storefront/order_success.html', ctx)


def _normalize_phone(phone):
    """Strip spaces, dashes, +977/0 prefix for flexible phone matching."""
    p = phone.replace(' ', '').replace('-', '')
    if p.startswith('+977'):
        p = p[4:]
    if p.startswith('977') and len(p) > 10:
        p = p[3:]
    return p.lstrip('0') or p


def track_order(request):
    company = _get_company(request)
    _require_ecom_enabled(company)
    order = None
    delivery_note = None
    order_number = request.GET.get('order_number', '').strip()
    phone = request.GET.get('phone', '').strip()

    if order_number and phone:
        norm_phone = _normalize_phone(phone)

        # 1. Try direct EC order number match
        order = EcomOrder.objects.filter(
            order_number__iexact=order_number,
            company=company,
        ).first()

        # 2. If not found, try by delivery note number (DN-YYYY-XXXX)
        if not order:
            from apps.orders.models import DeliveryNote
            dn = DeliveryNote.objects.filter(
                delivery_number__iexact=order_number,
                company=company,
            ).select_related('sales_order__ecom_order').first()
            if dn and hasattr(dn.sales_order, 'ecom_order'):
                order = dn.sales_order.ecom_order

        # 3. Verify phone matches (normalized comparison)
        if order:
            stored_norm = _normalize_phone(order.customer_phone or '')
            if stored_norm != norm_phone:
                order = None

    if order and order.sales_order:
        delivery_note = (
            order.sales_order.delivery_notes
            .order_by('-created_at')
            .first()
        )

    status_rank = {
        'PENDING': 1,
        'CONFIRMED': 1,
        'PROCESSING': 2,
        'DISPATCHED': 3,
        'DELIVERED': 4,
        'CANCELLED': 0,
    }
    if delivery_note:
        delivery_rank = {
            'PENDING': 1,
            'PACKED': 2,
            'DISPATCHED': 3,
            'IN_TRANSIT': 3,
            'OUT_FOR_DELIVERY': 3,
            'DELIVERED': 4,
            'FAILED': 3,
            'RETURNED': 3,
            'CANCELLED': 0,
        }
        current_step = delivery_rank.get(delivery_note.status, status_rank.get(order.status, 1))
        tracking_status_label = delivery_note.get_status_display()
    elif order:
        current_step = status_rank.get(order.status, 1)
        tracking_status_label = 'Out with Rider' if order.status == 'DISPATCHED' else order.get_status_display()
    else:
        current_step = 1
        tracking_status_label = ''

    ctx = _cms_context(company)
    ctx.update({
        'company': company,
        'order': order,
        'delivery_note': delivery_note,
        'current_step': current_step,
        'tracking_status_label': tracking_status_label,
        'cart_count': sum(_get_cart(request).values()),
    })
    return render(request, 'ecom/storefront/track_order.html', ctx)


def static_page(request, slug):
    """Render a CMS page by slug (About, Policies, etc.)."""
    company = _get_company(request)
    _require_ecom_enabled(company)
    page = get_object_or_404(Page, company=company, slug=slug, is_published=True)
    ctx = _cms_context(company)
    ctx.update({
        'company': company,
        'page': page,
        'cart_count': sum(_get_cart(request).values()),
    })
    return render(request, 'ecom/storefront/static_page.html', ctx)


# ──────────────────────────────────────────────────────────
# Product list (shop grid)
# ──────────────────────────────────────────────────────────

def product_list(request):
    company = _get_company(request)
    _require_ecom_enabled(company)

    category_id = request.GET.get('category', '').strip()
    search = request.GET.get('q', '').strip()
    sort = request.GET.get('sort', 'newest')
    colors_param = request.GET.get('colors', '')
    selected_colors = [c.strip() for c in colors_param.split(',') if c.strip()]
    view_mode = request.GET.get('view', 'grid')

    try:
        per_page = int(request.GET.get('per_page', 12))
        if per_page not in (8, 12, 16, 24):
            per_page = 12
    except (ValueError, TypeError):
        per_page = 12

    try:
        price_min = float(request.GET.get('price_min', ''))
    except (ValueError, TypeError):
        price_min = None
    try:
        price_max = float(request.GET.get('price_max', ''))
    except (ValueError, TypeError):
        price_max = None

    qs = Product.objects.filter(
        company=company, show_on_ecom=True
    ).select_related('category').prefetch_related('images', 'productstock')

    ctx = _cms_context(company)
    selected_category_name = None
    if category_id:
        qs = qs.filter(category_id=category_id)
        cat = next((c for c in ctx['categories'] if str(c.id) == str(category_id)), None)
        if cat:
            selected_category_name = cat.name
    if search:
        qs = qs.filter(name__icontains=search)
    if selected_colors:
        from django.db.models import Q
        color_q = Q()
        for c in selected_colors:
            color_q |= Q(color__iexact=c)
        qs = qs.filter(color_q)
    if price_min is not None:
        qs = qs.filter(price__gte=price_min)
    if price_max is not None:
        qs = qs.filter(price__lte=price_max)

    sort_map = {
        'az':       'name',
        'za':       '-name',
        'newest':   '-created_at',
        'oldest':   'created_at',
        'cheapest': 'price',
        'expensive':'-price',
    }
    qs = qs.order_by(sort_map.get(sort, '-created_at'))

    # Collect all available colors for the filter sidebar
    from django.db.models import Min, Max
    all_colors = (
        Product.objects.filter(company=company, show_on_ecom=True)
        .exclude(color='').values_list('color', flat=True).distinct().order_by('color')
    )
    price_bounds = Product.objects.filter(company=company, show_on_ecom=True).aggregate(
        lo=Min('price'), hi=Max('price')
    )

    paginator = Paginator(qs, per_page)
    page_obj = paginator.get_page(request.GET.get('page'))

    # Build a param string for pagination links that preserves all active filters
    filter_params = request.GET.copy()
    filter_params.pop('page', None)
    filter_qs = filter_params.urlencode()

    cart = _get_cart(request)
    ctx.update({
        'company': company,
        'products': page_obj,
        'page_obj': page_obj,
        'is_paginated': paginator.num_pages > 1,
        'selected_category': category_id,
        'selected_category_name': selected_category_name,
        'search': search,
        'sort': sort,
        'per_page': per_page,
        'view_mode': view_mode,
        'selected_colors': selected_colors,
        'colors_param': colors_param,
        'all_colors': list(all_colors),
        'price_min': price_min,
        'price_max': price_max,
        'price_lo': float(price_bounds['lo'] or 0),
        'price_hi': float(price_bounds['hi'] or 0),
        'filter_qs': filter_qs,
        'cart_count': sum(cart.values()),
    })
    # Return only the product grid partial for HTMX requests
    if request.headers.get('HX-Request'):
        return render(request, 'ecom/storefront/_product_grid.html', ctx)
    return render(request, 'ecom/storefront/product_list.html', ctx)


def image_search(request):
    from apps.products.image_search import search_by_image
    company = _get_company(request)
    _require_ecom_enabled(company)

    products = []
    error = None
    _ALLOWED_IMAGE_TYPES = {'image/jpeg', 'image/png', 'image/webp', 'image/gif'}
    _MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB

    if request.method == 'POST' and request.FILES.get('image'):
        img = request.FILES['image']
        if img.content_type not in _ALLOWED_IMAGE_TYPES:
            error = 'Unsupported image type. Please upload a JPEG, PNG, WebP, or GIF.'
        elif img.size > _MAX_IMAGE_BYTES:
            error = 'Image too large. Maximum size is 5 MB.'
        else:
            try:
                products = search_by_image(img, company)
            except Exception:
                error = 'Could not process image. Please try a different one.'

    cart = _get_cart(request)
    ctx = _cms_context(company)
    ctx.update({
        'company': company,
        'products': products,
        'is_paginated': False,
        'selected_category': None,
        'selected_category_name': 'Image Search Results',
        'search': '',
        'image_search_error': error,
        'cart_count': sum(cart.values()),
    })
    return render(request, 'ecom/storefront/product_list.html', ctx)


# ──────────────────────────────────────────────────────────
# Blog
# ──────────────────────────────────────────────────────────

def blog_list(request):
    company = _get_company(request)
    _require_ecom_enabled(company)

    posts = BlogPost.objects.filter(company=company, is_published=True)
    paginator = Paginator(posts, 9)
    page_obj = paginator.get_page(request.GET.get('page'))

    cart = _get_cart(request)
    ctx = _cms_context(company)
    ctx.update({
        'company': company,
        'posts': page_obj,
        'page_obj': page_obj,
        'is_paginated': paginator.num_pages > 1,
        'cart_count': sum(cart.values()),
    })
    return render(request, 'ecom/storefront/blog_list.html', ctx)


def blog_detail(request, slug):
    company = _get_company(request)
    _require_ecom_enabled(company)
    post = get_object_or_404(BlogPost, company=company, slug=slug, is_published=True)
    cart = _get_cart(request)
    ctx = _cms_context(company)
    ctx.update({
        'company': company,
        'post': post,
        'cart_count': sum(cart.values()),
    })
    return render(request, 'ecom/storefront/blog_detail.html', ctx)


# ──────────────────────────────────────────────────────────
# Contact
# ──────────────────────────────────────────────────────────

def contact_us(request):
    company = _get_company(request)
    _require_ecom_enabled(company)
    sent = False

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        email = request.POST.get('email', '').strip()
        phone = request.POST.get('phone', '').strip()
        subject = request.POST.get('subject', '').strip()
        message_text = request.POST.get('message', '').strip()

        if name and message_text:
            ContactMessage.objects.create(
                company=company,
                name=name,
                email=email,
                phone=phone,
                subject=subject,
                message=message_text,
            )
            sent = True

    cart = _get_cart(request)
    ctx = _cms_context(company)
    ctx.update({
        'company': company,
        'sent': sent,
        'cart_count': sum(cart.values()),
    })
    return render(request, 'ecom/storefront/contact.html', ctx)


# ──────────────────────────────────────────────────────────
# Customer auth
# ──────────────────────────────────────────────────────────

def customer_login(request):
    company = _get_company(request)
    _require_ecom_enabled(company)

    if request.user.is_authenticated and not request.user.is_staff:
        return redirect('ecom:account')

    from django.conf import settings as dj_settings
    recaptcha_site_key = getattr(dj_settings, 'RECAPTCHA_SITE_KEY', '')
    recaptcha_secret   = getattr(dj_settings, 'RECAPTCHA_SECRET_KEY', '')
    google_client_id   = getattr(dj_settings, 'SOCIAL_AUTH_GOOGLE_OAUTH2_KEY', '')

    form_errors = None
    if request.method == 'POST':
        # reCAPTCHA v3 — only validate if keys are configured
        if recaptcha_site_key and recaptcha_secret:
            import urllib.request, urllib.parse
            token = request.POST.get('g-recaptcha-response', '')
            data  = urllib.parse.urlencode({'secret': recaptcha_secret, 'response': token}).encode()
            try:
                resp = urllib.request.urlopen('https://www.google.com/recaptcha/api/siteverify', data, timeout=5)
                import json as _json
                result = _json.loads(resp.read())
                if not result.get('success') or result.get('score', 1) < 0.5:
                    form_errors = 'Security check failed. Please try again.'
            except Exception:
                pass  # network failure — don't block login

        if not form_errors:
            username = request.POST.get('username', '').strip()
            password = request.POST.get('password', '').strip()
            user = authenticate(request, username=username, password=password)
            if user and not user.is_staff:
                login(request, user)
                return redirect(request.GET.get('next', 'ecom:account'))
            else:
                form_errors = 'Invalid email/username or password.'

    cart = _get_cart(request)
    ctx = _cms_context(company)
    ctx.update({
        'company': company,
        'form_errors': form_errors,
        'cart_count': sum(cart.values()),
        'recaptcha_site_key': recaptcha_site_key,
        'google_login_enabled': bool(google_client_id),
    })
    return render(request, 'ecom/storefront/login.html', ctx)


def customer_register(request):
    company = _get_company(request)
    _require_ecom_enabled(company)

    if request.user.is_authenticated and not request.user.is_staff:
        return redirect('ecom:account')

    form_errors = None
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        email = request.POST.get('email', '').strip()
        phone = request.POST.get('phone', '').strip()
        password1 = request.POST.get('password1', '')
        password2 = request.POST.get('password2', '')

        if not name or not email or not password1:
            form_errors = 'Name, email, and password are required.'
        elif password1 != password2:
            form_errors = 'Passwords do not match.'
        elif len(password1) < 8:
            form_errors = 'Password must be at least 8 characters.'
        elif User.objects.filter(username=email).exists():
            form_errors = 'An account with this email already exists.'
        else:
            user = User.objects.create_user(
                username=email,
                email=email,
                password=password1,
                first_name=name,
            )
            # Create/link customer profile
            from apps.customers.models import Customer
            Customer.objects.get_or_create(
                company=company, email=email,
                defaults={'name': name, 'phone': phone or ''}
            )
            login(request, user)
            return redirect('ecom:account')

    cart = _get_cart(request)
    ctx = _cms_context(company)
    ctx.update({
        'company': company,
        'form_errors': form_errors,
        'cart_count': sum(cart.values()),
    })
    return render(request, 'ecom/storefront/register.html', ctx)


def customer_logout(request):
    logout(request)
    return redirect('ecom:home')


def customer_account(request):
    company = _get_company(request)
    _require_ecom_enabled(company)

    if not request.user.is_authenticated or request.user.is_staff:
        from django.urls import reverse
        return redirect(f"{reverse('ecom:login')}?next={request.path}")

    orders = EcomOrder.objects.filter(
        company=company, customer_email=request.user.email
    ).prefetch_related('items__product').order_by('-created_at')

    cart = _get_cart(request)
    order_count = orders.count()
    ctx = _cms_context(company)
    ctx.update({
        'company': company,
        'orders': orders,
        'order_count': order_count,
        'reminder_count': 3,
        'saved_address_count': 2,
        'cart_count': sum(cart.values()),
    })
    return render(request, 'ecom/storefront/account.html', ctx)


def custom_404(request, exception=None):
    company = _get_company(request)
    ctx = {'company': company, 'cart_count': sum(_get_cart(request).values())}
    if company:
        ctx.update(_cms_context(company))
    return render(request, 'ecom/storefront/404.html', ctx, status=404)


# ── Bundle / Package storefront views ────────────────────────────────────────

def bundle_list(request):
    from apps.products.models import Package
    company = _get_company(request)
    _require_ecom_enabled(company)
    bundles = Package.objects.filter(company=company, show_on_ecom=True).prefetch_related('items__product')
    cart = _get_cart(request)
    ctx = _cms_context(company)
    ctx.update({'company': company, 'bundles': bundles, 'cart_count': sum(cart.values())})
    return render(request, 'ecom/storefront/bundle_list.html', ctx)


def bundle_detail(request, bundle_id):
    from apps.products.models import Package
    company = _get_company(request)
    _require_ecom_enabled(company)
    bundle = get_object_or_404(Package, id=bundle_id, company=company, show_on_ecom=True)
    cart = _get_cart(request)

    # Categorise items by type for the customisation UI
    all_items = bundle.items.select_related('product').prefetch_related(
        'product__images', 'product__productstock'
    ).all()
    core_items     = [i for i in all_items if i.item_type == 'core']
    optional_items = [i for i in all_items if i.item_type == 'optional']
    addon_items    = [i for i in all_items if i.item_type == 'addon']

    # Base price = sum of core items only (optional/addon are extras)
    core_total = sum(
        float(i.product.price) * (i.quantity or 1)
        for i in core_items if i.product
    )

    ctx = _cms_context(company)
    ctx.update({
        'company': company,
        'bundle': bundle,
        'cart_count': sum(cart.values()),
        'core_items': core_items,
        'optional_items': optional_items,
        'addon_items': addon_items,
        'core_total': core_total,
        'core_count': len(core_items),
        'optional_count': len(optional_items),
        'addon_count': len(addon_items),
    })
    return render(request, 'ecom/storefront/bundle_detail.html', ctx)


@require_POST
def add_bundle_to_cart(request, bundle_id):
    from apps.products.models import Package
    company = _get_company(request)
    bundle = get_object_or_404(Package, id=bundle_id, company=company, show_on_ecom=True)
    cart = _get_cart(request)
    skipped = []

    # Customer's optional/addon selections from the customisation form
    selected_optional = set(request.POST.getlist('optional_items'))
    selected_addon    = set(request.POST.getlist('addon_items'))

    for item in bundle.items.select_related('product__productstock').all():
        if not item.product or not item.product.show_on_ecom:
            continue

        # Determine whether this item should be included
        pid_str = str(item.product.id)
        if item.item_type == 'core':
            include = True
        elif item.item_type == 'optional':
            # included if the customer left it checked (pid in selected_optional)
            # If the form submitted nothing for optional_items at all, default to include
            if selected_optional:
                include = pid_str in selected_optional
            else:
                include = True  # legacy: no selection = add all
        elif item.item_type == 'addon':
            include = pid_str in selected_addon
        else:
            include = True

        if not include:
            continue

        qty = item.quantity or 1
        try:
            avail = item.product.productstock.ecom_stock
        except Exception:
            avail = 0

        current = cart.get(pid_str, 0)
        if avail > 0 and current + qty <= avail:
            cart[pid_str] = current + qty
        else:
            skipped.append(item.product.name)

    _save_cart(request, cart)
    if skipped:
        messages.warning(request, f'Some items were not added (out of stock): {", ".join(skipped)}')
    else:
        messages.success(request, f'"{bundle.name}" added to cart.')
    return redirect('ecom:cart')
