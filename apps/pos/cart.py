"""
apps/pos/cart.py
================
Session-based POS cart.

The cart lives entirely in request.session under the key 'pos_cart'.
No database writes happen until checkout.

Cart structure (stored in session)
-----------------------------------
{
    "items": {
        "<product_id>": {
            "product_id":   str,
            "name":         str,
            "price":        str,   # Decimal serialised as string
            "quantity":     int,
            "discount_pct": str,   # "0.00"
            "line_total":   str,   # price * qty * (1 - discount_pct/100)
        },
        ...
    },
    "discount_pct":  str,   # cart-level discount %
    "tax_pct":       str,   # tax % (pre-filled from company.tax_rate)
    "customer_id":   str | null,
    "referrer_id":   str | null,   # loyalty referrer credited with the sale — not printed on receipt
}
"""

from decimal import Decimal, ROUND_HALF_UP

SESSION_KEY = 'pos_cart'


def _q(value) -> Decimal:
    """Quantise to 2 decimal places."""
    return Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def get_cart(request) -> dict:
    """Return the current cart dict, initialising if absent."""
    if SESSION_KEY not in request.session:
        request.session[SESSION_KEY] = {
            'items': {},
            'discount_pct': '0.00',
            'tax_pct': '0.00',
            'delivery_charge': '0.00',
            'customer_id': None,
            'referrer_id': None,
        }
    return request.session[SESSION_KEY]


def _save(request, cart: dict):
    """Persist the cart back to the session."""
    request.session[SESSION_KEY] = cart
    request.session.modified = True


def add_item(request, product, quantity: int = 1, discount_pct: Decimal = Decimal('0')) -> dict:
    """
    Add *quantity* units of *product* to the cart.
    If the product is already in the cart, increment the quantity.
    Returns the updated cart.
    """
    cart = get_cart(request)
    pid = str(product.id)
    qty = max(1, int(quantity))
    disc = _q(discount_pct)

    item = cart['items'].pop(pid, None)
    if item:
        item['quantity'] += qty
    else:
        item = {
            'product_id':   pid,
            'name':         product.name,
            'price':        str(_q(product.price)),
            'quantity':     qty,
            'discount_pct': str(disc),
            'line_total':   '0.00',
            'image_url':    product.primary_image_url,
        }

    _recalc_item(item)
    # Move to the front so the most recently added item shows first in the cart.
    cart['items'] = {pid: item, **cart['items']}
    _save(request, cart)
    return cart


def update_item_qty(request, product_id: str, quantity: int) -> dict:
    """Set the quantity of a cart item. Removes it if quantity <= 0."""
    cart = get_cart(request)
    if product_id in cart['items']:
        if quantity <= 0:
            del cart['items'][product_id]
        else:
            cart['items'][product_id]['quantity'] = quantity
            _recalc_item(cart['items'][product_id])
    _save(request, cart)
    return cart


def remove_item(request, product_id: str) -> dict:
    """Remove a product from the cart entirely."""
    cart = get_cart(request)
    cart['items'].pop(product_id, None)
    _save(request, cart)
    return cart


def set_discount(request, discount_pct: Decimal) -> dict:
    """Set the cart-level discount percentage."""
    cart = get_cart(request)
    cart['discount_pct'] = str(_q(discount_pct))
    _save(request, cart)
    return cart


def set_tax(request, tax_pct: Decimal) -> dict:
    """Set the cart-level tax percentage."""
    cart = get_cart(request)
    cart['tax_pct'] = str(_q(tax_pct))
    _save(request, cart)
    return cart


def set_customer(request, customer_id) -> dict:
    """Assign a customer to the cart (None = walk-in / cash sale)."""
    cart = get_cart(request)
    cart['customer_id'] = str(customer_id) if customer_id else None
    _save(request, cart)
    return cart


def set_referrer(request, referrer_id) -> dict:
    """Assign a loyalty referrer to the cart (None = no referral)."""
    cart = get_cart(request)
    cart['referrer_id'] = str(referrer_id) if referrer_id else None
    _save(request, cart)
    return cart


def set_delivery_charge(request, amount: Decimal) -> dict:
    """Set a flat delivery charge on the cart (0 = no delivery fee)."""
    cart = get_cart(request)
    cart['delivery_charge'] = str(_q(max(Decimal('0'), amount)))
    _save(request, cart)
    return cart


def clear_cart(request):
    """Wipe the cart from the session."""
    request.session.pop(SESSION_KEY, None)
    request.session.modified = True


def get_totals(cart: dict) -> dict:
    """
    Compute subtotal, discount, tax, and grand total from the cart dict.
    Returns a dict with Decimal values.
    """
    subtotal = sum(
        Decimal(item['line_total']) for item in cart['items'].values()
    )
    disc_pct = Decimal(cart.get('discount_pct', '0'))
    tax_pct  = Decimal(cart.get('tax_pct',      '0'))

    delivery  = _q(Decimal(cart.get('delivery_charge', '0') or '0'))
    discount  = _q(subtotal * disc_pct / Decimal('100'))
    taxable   = subtotal - discount
    tax       = _q(taxable * tax_pct / Decimal('100'))
    total     = _q(taxable + tax + delivery)

    return {
        'subtotal':        subtotal,
        'discount_pct':    disc_pct,
        'discount_amount': discount,
        'tax_pct':         tax_pct,
        'tax_amount':      tax,
        'delivery_charge': delivery,
        'total':           total,
        'item_count':      sum(i['quantity'] for i in cart['items'].values()),
    }


# ── Internal helpers ──────────────────────────────────────────────────────────

def _recalc_item(item: dict):
    """Recompute line_total for a single item dict in-place."""
    price = Decimal(item['price'])
    qty   = Decimal(str(item['quantity']))
    disc  = Decimal(item['discount_pct'])
    base  = price * qty
    discount_amt = _q(base * disc / Decimal('100'))
    item['line_total'] = str(_q(base - discount_amt))
