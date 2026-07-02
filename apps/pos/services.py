"""
apps/pos/services.py
====================
POS checkout service — converts a session cart into an Invoice + Payment + POSSale
atomically inside a single DB transaction.

All bookkeeping (journal entries) is handled by the existing billing and
payments signals — this service does not touch the bookkeeping layer directly.
"""

import logging
from decimal import Decimal

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.billing.models import Invoice, InvoiceItem
from apps.billing.services.invoice_service import generate_invoice_number
from apps.customers.models import Customer
from apps.payments.models import Payment
from apps.payments.services.payment_number_service import generate_payment_number
from apps.pos.cart import get_totals
from apps.pos.models import POSSale, Referrer
from apps.products.models import Product, ProductStock, StockTransaction

logger = logging.getLogger(__name__)
audit = logging.getLogger('audit')


@transaction.atomic
def checkout(
    request,
    cart: dict,
    payment_method: str,
    amount_tendered: Decimal,
    notes: str = '',
) -> POSSale:
    """
    Convert the session cart into a completed POS sale.

    Steps
    -----
    1. Validate cart is not empty.
    2. Resolve customer (None = walk-in cash sale).
    3. Generate invoice_number + sequence_number.
    4. Create Invoice (status=ISSUED).
    5. Create InvoiceItems — each item.save() triggers calculate_total via signal.
    6. Refresh invoice totals.
    7. Create Payment (triggers journal entry via signal).
    8. Create POSSale audit record.
    9. Decrement ProductStock for non-service products.
    10. Clear the session cart.

    Returns
    -------
    POSSale instance.

    Raises
    ------
    ValueError  — cart empty, product not found, insufficient stock.
    """
    company = request.user_company
    user    = request.user

    if not cart.get('items'):
        raise ValueError("Cart is empty.")

    totals = get_totals(cart)
    delivery_charge = totals['delivery_charge']

    # ── 1. Resolve customer ───────────────────────────────────────────────────
    customer = None
    customer_id = cart.get('customer_id')
    if customer_id:
        try:
            customer = Customer.active_objects.get(pk=customer_id, company=company)
        except Customer.DoesNotExist:
            pass  # treat as walk-in if customer was deleted

    # ── 1b. Resolve referrer (loyalty tracking — never shown on the receipt) ──
    referrer = None
    referrer_id = cart.get('referrer_id')
    if referrer_id:
        try:
            referrer = Referrer.objects.get(pk=referrer_id, company=company)
        except Referrer.DoesNotExist:
            pass

    # ── 2. Generate invoice number ────────────────────────────────────────────
    is_vat = getattr(company, 'vat_registered', False)
    doc_type = 'INV' if is_vat else 'ORD'
    invoice_number, sequence_number, fy = generate_invoice_number(company.id, doc_type=doc_type)

    # ── 3. Create Invoice ─────────────────────────────────────────────────────
    today = timezone.now().date()
    invoice = Invoice.objects.create(
        company=company,
        branch=getattr(request, 'user_branch', None),
        customer=customer,
        invoice_number=invoice_number,
        sequence_number=sequence_number,
        fiscal_year=fy,
        transaction_date=today,
        discount_percent=Decimal(cart.get('discount_pct', '0')),
        tax_percent=Decimal(cart.get('tax_pct', '0')),
        status='ISSUED' if is_vat else 'ESTIMATE',
        total=Decimal('0.00'),   # recalculated after items
        created_by=user,
    )

    # ── 4. Create InvoiceItems ────────────────────────────────────────────────
    products_to_destock = []
    tracks_inventory = getattr(company, 'enable_inventory', False)

    for item_data in cart['items'].values():
        try:
            product = Product.active_objects.get(
                pk=item_data['product_id'], company=company
            )
        except Product.DoesNotExist:
            raise ValueError(f"Product '{item_data['name']}' not found.")

        qty = int(item_data['quantity'])

        # Stock check only for inventory-tracking companies with physical products
        if tracks_inventory and not product.is_service:
            try:
                stock = ProductStock.objects.get(product=product)
                if stock.stock < qty:
                    raise ValueError(
                        f"Insufficient stock for '{product.name}': "
                        f"available {stock.stock}, requested {qty}."
                    )
                products_to_destock.append((product, qty))
            except ProductStock.DoesNotExist:
                # No stock record — allow sale (treat as unlimited)
                pass

        InvoiceItem.objects.create(
            invoice=invoice,
            product=product,
            quantity=qty,
            price=Decimal(item_data['price']),
            discount_percent=Decimal(item_data['discount_pct']),
        )

    # ── 5a. Add delivery charge as a line item so it appears on the receipt ──
    if delivery_charge > Decimal('0.00'):
        InvoiceItem.objects.create(
            invoice=invoice,
            description='Delivery Charge',
            quantity=1,
            price=delivery_charge,
            discount_percent=Decimal('0.00'),
        )

    # ── 5. Refresh invoice totals (InvoiceItem.save() already called calculate_total) ──
    invoice.refresh_from_db()

    # ── 6. Create Payment ─────────────────────────────────────────────────────
    try:
        reference_number, _, pay_fy = generate_payment_number(company.id, 'CUSTOMER')
    except Exception:
        reference_number = None

    payment = Payment.objects.create(
        company=company,
        branch=getattr(request, 'user_branch', None),
        invoice=invoice,
        date=today,
        amount=invoice.total,
        amount_applied=invoice.total,
        discount_amount=invoice.discount_amount,
        method=payment_method,
        payment_type='CUSTOMER',
        reference_number=reference_number,
        fiscal_year=pay_fy,
        description=f'POS sale — {invoice.invoice_number}',
        created_by=user,
    )

    # Update outstanding balance to zero (fully paid at counter)
    invoice.outstanding_balance = Decimal('0.00')
    invoice.save(update_fields=['outstanding_balance'])

    # ── 7. Create POSSale ─────────────────────────────────────────────────────
    change_given = max(Decimal('0'), amount_tendered - invoice.total)

    pos_sale = POSSale.objects.create(
        company=company,
        branch=getattr(request, 'user_branch', None),
        invoice=invoice,
        customer=customer,
        referred_by=referrer,
        payment_method=payment_method,
        amount_tendered=amount_tendered,
        change_given=change_given,
        subtotal=invoice.subtotal,
        discount_amount=invoice.discount_amount,
        tax_amount=invoice.tax_amount,
        delivery_charge=delivery_charge,
        total=invoice.total,
        notes=notes,
        created_by=user,
    )

    # ── 8. Decrement stock ────────────────────────────────────────────────────
    for product, qty in products_to_destock:
        ProductStock.objects.filter(product=product).update(
            stock=F('stock') - qty
        )
        StockTransaction.objects.create(
            product=product,
            user=user,
            transaction_type='REMOVE',
            quantity=qty,
            reason=f'POS sale {invoice.invoice_number}',
        )

    audit.info(
        'POS_CHECKOUT actor=%s company=%s invoice=%s total=%s method=%s',
        user.email, company.name, invoice.invoice_number, invoice.total, payment_method,
    )

    return pos_sale
