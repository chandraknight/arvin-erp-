"""
apps/pos/views.py
=================
Point of Sale views.

All views are protected with @auth_required or @login_required.
All querysets are scoped to request.user_company.

URL namespace: pos

Views
-----
pos_terminal        GET   /pos/                  — main POS screen
pos_add_item        POST  /pos/cart/add/         — HTMX: add product to cart
pos_update_qty      POST  /pos/cart/update/      — HTMX: change item quantity
pos_remove_item     POST  /pos/cart/remove/      — HTMX: remove item from cart
pos_set_customer    POST  /pos/cart/customer/    — HTMX: assign/clear customer
pos_set_referrer    POST  /pos/cart/referrer/    — HTMX: assign/clear loyalty referrer
pos_create_referrer POST  /pos/cart/referrer/new/ — HTMX: quick-create + select a referrer
pos_referrer_search GET   /pos/api/referrers/     — JSON referrer search (name/phone)
pos_set_discount    POST  /pos/cart/discount/    — HTMX: set cart discount %
pos_clear_cart      POST  /pos/cart/clear/       — HTMX: empty the cart
pos_checkout        POST  /pos/checkout/         — process payment & create invoice
pos_receipt         GET   /pos/receipt/<uuid>/   — receipt after checkout
pos_sale_list       GET   /pos/sales/            — today's POS sales list
pos_product_search  GET   /pos/api/products/     — JSON product search
"""

import json
import logging
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.customers.models import Customer
from apps.products.models import Category, CategoryType, Product
from apps.utils.amount_words import amount_in_words
from apps.utils.constant import PAYMENT_METHOD_CHOICES
from apps.utils.decorator import auth_required

from .cart import (
    add_item, clear_cart, get_cart, get_totals,
    remove_item, set_customer, set_delivery_charge, set_discount, set_referrer, set_tax, update_item_qty,
)
from .models import POSSale, Referrer
from .services import checkout

logger = logging.getLogger(__name__)


# ── Guard ─────────────────────────────────────────────────────────────────────

def _require_pos(request):
    """Redirect if POS module is not enabled for this company."""
    company = request.user_company
    if company and not company.enable_pos:
        messages.warning(request, "POS module is not enabled for your company.")
        return redirect('accounts:user_dashboard')
    return None


# ── Main terminal ─────────────────────────────────────────────────────────────

@auth_required('pos.add_possale')
def pos_terminal(request):
    """
    Main POS screen.
    Left panel: product grid with category filter.
    Right panel: live cart (rendered server-side, swapped by HTMX).
    """
    guard = _require_pos(request)
    if guard:
        return guard

    company = request.user_company
    if company is None:
        messages.warning(request, "POS requires a company context. Please log in as a company user.")
        return redirect('accounts:user_dashboard')

    # Category types for the filter tabs
    category_types = CategoryType.active_objects.filter(company=company).order_by('name')

    # Selected category type (from query param)
    selected_ct_id = request.GET.get('ct', '')
    selected_category_id = request.GET.get('cat', '')

    # Categories under the selected type
    categories = []
    if selected_ct_id:
        categories = Category.active_objects.filter(
            company=company, type_id=selected_ct_id
        ).order_by('name')

    # Products — annotate with current stock for display
    from django.db.models import OuterRef, Subquery, IntegerField
    from apps.products.models import ProductStock as _PS
    stock_sq = _PS.objects.filter(product=OuterRef('pk')).values('stock')[:1]
    products_qs = Product.active_objects.filter(company=company).annotate(
        current_stock=Subquery(stock_sq, output_field=IntegerField())
    ).prefetch_related('images').order_by('name')
    if selected_category_id:
        products_qs = products_qs.filter(category_id=selected_category_id)
    elif selected_ct_id:
        products_qs = products_qs.filter(category__type_id=selected_ct_id)

    # Search
    q = request.GET.get('q', '').strip()
    if q:
        from django.db.models import Q
        products_qs = products_qs.filter(
            Q(name__icontains=q) | Q(barcode__icontains=q) | Q(sku__icontains=q)
        )

    # Paginate products (24 per page — 4×6 grid)
    paginator = Paginator(products_qs, 24)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    # Cart
    cart = get_cart(request)
    # Pre-fill tax from company if cart is fresh — only for VAT-registered companies
    if cart.get('tax_pct', '0.00') == '0.00' and company and company.vat_registered and company.tax_rate:
        set_tax(request, company.tax_rate)
        cart = get_cart(request)

    totals = get_totals(cart)

    # Customers for the customer selector
    customers = Customer.active_objects.filter(company=company).order_by('name')[:100]

    selected_referrer = None
    if cart.get('referrer_id'):
        selected_referrer = Referrer.objects.filter(pk=cart['referrer_id'], company=company).first()

    context = {
        'category_types':      category_types,
        'selected_ct_id':      selected_ct_id,
        'selected_category_id': selected_category_id,
        'categories':          categories,
        'page_obj':            page_obj,
        'q':                   q,
        'cart':                cart,
        'totals':              totals,
        'customers':           customers,
        'payment_methods':     PAYMENT_METHOD_CHOICES,
        'company':             company,
        'selected_referrer':   selected_referrer,
    }

    # HTMX partial refresh — return only the product grid
    if request.headers.get('HX-Request') and request.GET.get('partial') == 'products':
        return render(request, 'pos/partials/product_grid.html', context)

    return render(request, 'pos/terminal.html', context)


# ── Cart HTMX endpoints ───────────────────────────────────────────────────────

@require_POST
@auth_required('pos.add_possale')
def pos_add_item(request):
    """HTMX POST — add a product to the cart, return updated cart partial."""
    guard = _require_pos(request)
    if guard:
        return guard

    company = request.user_company
    product_id = request.POST.get('product_id', '').strip()
    try:
        qty = max(1, int(request.POST.get('quantity', 1)))
    except (ValueError, TypeError):
        qty = 1

    try:
        product = Product.active_objects.select_related('productstock').get(pk=product_id, company=company)
    except Product.DoesNotExist:
        return HttpResponse(
            '<p class="text-red-600 text-sm p-2">Product not found.</p>', status=404
        )

    stock_warning = None
    if not product.is_service:
        available = getattr(product, 'productstock', None)
        available = available.stock if available else 0
        already_in_cart = int(get_cart(request)['items'].get(str(product.id), {}).get('quantity', 0))
        can_add = max(0, available - already_in_cart)
        if can_add <= 0:
            stock_warning = f'"{product.name}" is out of stock (POS stock: {available}).'
            qty = 0
        elif qty > can_add:
            stock_warning = f'Only {available} unit(s) of "{product.name}" in stock — added {can_add}.'
            qty = can_add

    cart = add_item(request, product, quantity=qty) if qty > 0 else get_cart(request)
    return _cart_partial(request, cart, stock_warning=stock_warning)


@require_POST
@auth_required('pos.add_possale')
def pos_update_qty(request):
    """HTMX POST — update quantity of a cart item."""
    guard = _require_pos(request)
    if guard:
        return guard

    product_id = request.POST.get('product_id', '').strip()
    try:
        qty = int(request.POST.get('quantity', 1))
    except (ValueError, TypeError):
        qty = 1

    stock_warning = None
    if qty > 0:
        try:
            product = Product.active_objects.select_related('productstock').get(
                pk=product_id, company=request.user_company
            )
        except Product.DoesNotExist:
            product = None
        if product and not product.is_service:
            available = getattr(product, 'productstock', None)
            available = available.stock if available else 0
            if qty > available:
                stock_warning = f'Only {available} unit(s) of "{product.name}" in stock.'
                qty = available

    cart = update_item_qty(request, product_id, qty)
    return _cart_partial(request, cart, stock_warning=stock_warning)


@require_POST
@auth_required('pos.add_possale')
def pos_remove_item(request):
    """HTMX POST — remove a product from the cart."""
    guard = _require_pos(request)
    if guard:
        return guard

    product_id = request.POST.get('product_id', '').strip()
    cart = remove_item(request, product_id)
    return _cart_partial(request, cart)


@require_POST
@auth_required('pos.add_possale')
def pos_set_customer(request):
    """HTMX POST — assign or clear the customer on the cart."""
    guard = _require_pos(request)
    if guard:
        return guard

    customer_id = request.POST.get('customer_id', '').strip() or None
    cart = set_customer(request, customer_id)
    return _cart_partial(request, cart)


@require_POST
@auth_required('pos.add_possale')
def pos_set_referrer(request):
    """HTMX POST — assign or clear the loyalty referrer on the cart."""
    guard = _require_pos(request)
    if guard:
        return guard

    referrer_id = request.POST.get('referrer_id', '').strip() or None
    cart = set_referrer(request, referrer_id)
    return _cart_partial(request, cart)


@require_POST
@auth_required('pos.add_possale')
def pos_create_referrer(request):
    """HTMX POST — quick-create a referrer (when typed name/phone has no match) and select it."""
    guard = _require_pos(request)
    if guard:
        return guard

    company = request.user_company
    name = request.POST.get('name', '').strip()
    phone = request.POST.get('phone', '').strip()
    if not name:
        return _cart_partial(request, get_cart(request), stock_warning='Referrer name is required.')

    referrer = Referrer.objects.create(company=company, name=name, phone=phone, created_by=request.user)
    cart = set_referrer(request, str(referrer.id))
    return _cart_partial(request, cart)


@login_required
def pos_referrer_search(request):
    """JSON endpoint — type-ahead search for referrers by name or phone."""
    company = request.user_company
    if not company:
        return JsonResponse({'referrers': []})

    q = request.GET.get('q', '').strip()
    if not q:
        return JsonResponse({'referrers': []})

    from django.db.models import Q
    referrers = list(
        Referrer.objects.filter(company=company)
        .filter(Q(name__icontains=q) | Q(phone__icontains=q))
        .order_by('name')
        .values('id', 'name', 'phone')[:10]
    )
    return JsonResponse({'referrers': referrers})


@require_POST
@auth_required('pos.add_possale')
def pos_set_discount(request):
    """HTMX POST — set cart-level discount %."""
    guard = _require_pos(request)
    if guard:
        return guard

    try:
        disc = Decimal(request.POST.get('discount_pct', '0'))
        disc = max(Decimal('0'), min(Decimal('100'), disc))
    except InvalidOperation:
        disc = Decimal('0')

    cart = set_discount(request, disc)
    return _cart_partial(request, cart)


@require_POST
@login_required
def pos_set_delivery_charge(request):
    """HTMX POST — set a flat delivery charge on the cart."""
    guard = _require_pos(request)
    if guard:
        return guard

    try:
        amount = Decimal(request.POST.get('delivery_charge', '0'))
        amount = max(Decimal('0'), amount)
    except InvalidOperation:
        amount = Decimal('0')

    cart = set_delivery_charge(request, amount)
    return _cart_partial(request, cart)


@require_POST
@login_required
def pos_clear_cart(request):
    """HTMX POST — empty the cart."""
    clear_cart(request)
    cart = get_cart(request)
    return _cart_partial(request, cart)


# ── Checkout ──────────────────────────────────────────────────────────────────

@require_POST
@auth_required('pos.add_possale')
def pos_checkout(request):
    """
    Process payment and create Invoice + Payment + POSSale atomically.
    On success: redirect to receipt page.
    On error: re-render terminal with error message.
    """
    guard = _require_pos(request)
    if guard:
        return guard

    cart = get_cart(request)

    if not cart.get('items'):
        messages.error(request, "Cart is empty. Add products before checking out.")
        return redirect('pos:terminal')

    payment_method = request.POST.get('payment_method', '').strip()
    valid_methods = [m[0] for m in PAYMENT_METHOD_CHOICES]
    if payment_method not in valid_methods:
        messages.error(request, "Please select a valid payment method.")
        return redirect('pos:terminal')

    try:
        amount_tendered = Decimal(request.POST.get('amount_tendered', '0') or '0')
    except InvalidOperation:
        amount_tendered = Decimal('0')

    notes = request.POST.get('notes', '').strip()

    try:
        pos_sale = checkout(
            request=request,
            cart=cart,
            payment_method=payment_method,
            amount_tendered=amount_tendered,
            notes=notes,
        )
        clear_cart(request)
        messages.success(
            request,
            f"Sale complete — Invoice {pos_sale.invoice.invoice_number}."
        )
        return redirect('pos:receipt', pk=pos_sale.pk)

    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect('pos:terminal')

    except Exception as exc:
        logger.error('POS checkout error: %s', exc, exc_info=True)
        messages.error(request, f"Checkout failed: {exc}")
        return redirect('pos:terminal')


# ── Receipt ───────────────────────────────────────────────────────────────────

@auth_required('pos.view_possale')
def pos_receipt(request, pk):
    """Receipt page shown after a successful checkout."""
    guard = _require_pos(request)
    if guard:
        return guard

    sale = get_object_or_404(
        POSSale.active_objects.select_related(
            'invoice', 'customer', 'company'
        ).prefetch_related('invoice__items__product'),
        pk=pk,
        company=request.user_company,
    )
    return render(request, 'pos/receipt.html', {
        'sale': sale,
        'amount_in_words': amount_in_words(sale.total),
    })


# ── Sales list ────────────────────────────────────────────────────────────────

@auth_required('pos.view_possale')
def pos_sale_list(request):
    """Today's POS sales with date filter."""
    guard = _require_pos(request)
    if guard:
        return guard

    company = request.user_company
    qs = POSSale.active_objects.filter(company=company).select_related(
        'invoice', 'customer'
    ).order_by('-created_at')

    # Date filter
    date_str = request.GET.get('date', timezone.now().date().isoformat())
    try:
        from datetime import date
        filter_date = date.fromisoformat(date_str)
        qs = qs.filter(created_at__date=filter_date)
    except ValueError:
        filter_date = timezone.now().date()

    # Payment method filter
    method = request.GET.get('method', '').strip()
    if method:
        qs = qs.filter(payment_method=method)

    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    # Daily totals
    from django.db.models import Sum, Count
    daily = qs.aggregate(
        total_sales=Sum('total'),
        sale_count=Count('id'),
    )

    return render(request, 'pos/sale_list.html', {
        'page_obj':        page_obj,
        'filter_date':     filter_date,
        'method':          method,
        'payment_methods': PAYMENT_METHOD_CHOICES,
        'daily_total':     daily['total_sales'] or Decimal('0'),
        'daily_count':     daily['sale_count'] or 0,
    })


# ── Product search JSON API ───────────────────────────────────────────────────

@login_required
def pos_product_search(request):
    """
    JSON endpoint for barcode scanner / quick search.
    ?q=<name or barcode>
    Returns up to 20 matching products scoped to the user's company.
    """
    company = request.user_company
    if not company:
        return JsonResponse({'products': []})

    q = request.GET.get('q', '').strip()
    if not q:
        return JsonResponse({'products': []})

    from django.db.models import Q
    qs = Product.active_objects.filter(company=company)
    # Exact barcode/SKU match first (scanner input)
    if qs.filter(Q(barcode=q) | Q(sku=q)).exists():
        qs = qs.filter(Q(barcode=q) | Q(sku=q))
    else:
        qs = qs.filter(Q(name__icontains=q) | Q(barcode__icontains=q) | Q(sku__icontains=q))

    products = list(
        qs.values('id', 'name', 'price', 'barcode', 'sku', 'is_service')[:20]
    )
    from apps.products.models import ProductStock
    non_service_ids = [str(p['id']) for p in products if not p['is_service']]
    stock_map = {
        str(s.product_id): s.stock
        for s in ProductStock.objects.filter(product_id__in=non_service_ids)
    }
    for p in products:
        p['id'] = str(p['id'])
        p['price'] = str(p['price'])
        p['stock'] = stock_map.get(p['id'], 0) if not p['is_service'] else None

    return JsonResponse({'products': products})


# ── Internal helper ───────────────────────────────────────────────────────────

def _cart_partial(request, cart: dict, stock_warning: str = None) -> HttpResponse:
    """Render the cart sidebar partial and return as HTMX response."""
    totals = get_totals(cart)
    customers = Customer.active_objects.filter(
        company=request.user_company
    ).order_by('name')[:100]

    selected_referrer = None
    if cart.get('referrer_id'):
        selected_referrer = Referrer.objects.filter(
            pk=cart['referrer_id'], company=request.user_company
        ).first()

    html = render(request, 'pos/partials/cart.html', {
        'cart':              cart,
        'totals':            totals,
        'customers':         customers,
        'payment_methods':   PAYMENT_METHOD_CHOICES,
        'company':           request.user_company,
        'stock_warning':     stock_warning,
        'selected_referrer': selected_referrer,
    })
    return html
