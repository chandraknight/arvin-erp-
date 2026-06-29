"""
Creates a SalesOrder (apps/orders) from an EcomOrder so the order
flows through order management, delivery, and POS.
"""
import logging
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings

from apps.orders.models import SalesOrder, SalesOrderItem
from apps.customers.models import Customer

logger = logging.getLogger(__name__)


def get_or_create_ecom_customer(company, name, phone, email=None):
    """Find existing customer by phone, or create a walk-in ecom customer."""
    customer = Customer.objects.filter(company=company, phone=phone).first()
    if customer:
        return customer
    customer = Customer(
        company=company,
        name=name,
        phone=phone,
        email=email or None,
    )
    customer.save()
    return customer


@transaction.atomic
def create_sales_order_from_ecom(ecom_order):
    """
    Given a saved EcomOrder (with items), create a linked SalesOrder.
    Returns the SalesOrder instance.
    """
    if ecom_order.sales_order_id:
        return ecom_order.sales_order

    customer = ecom_order.customer
    if not customer:
        customer = get_or_create_ecom_customer(
            company=ecom_order.company,
            name=ecom_order.customer_name,
            phone=ecom_order.customer_phone,
            email=ecom_order.customer_email,
        )
        ecom_order.customer = customer

    # Generate SO order_number (same pattern as SalesOrderCreateView)
    count = SalesOrder.objects.filter(company=ecom_order.company).count() + 1
    so_number = f"SO-{timezone.now().year}-{count:04d}"
    while SalesOrder.objects.filter(order_number=so_number).exists():
        count += 1
        so_number = f"SO-{timezone.now().year}-{count:04d}"

    sales_order = SalesOrder(
        company=ecom_order.company,
        customer=customer,
        order_number=so_number,
        order_date=timezone.now().date(),
        status='DRAFT',
        notes=f"[ECOM #{ecom_order.order_number}] {ecom_order.notes or ''}".strip(),
        delivery_address=ecom_order.delivery_address,
        delivery_contact=ecom_order.customer_name,
        delivery_phone=ecom_order.customer_phone,
    )
    sales_order.save()

    subtotal = Decimal('0.00')
    for item in ecom_order.items.select_related('product'):
        SalesOrderItem.objects.create(
            order=sales_order,
            product=item.product,
            description=item.product.name,
            quantity=item.quantity,
            unit_price=item.unit_price,
        )
        subtotal += item.total_price

    delivery_charge = ecom_order.delivery_charge or Decimal('0.00')
    sales_order.subtotal = subtotal
    sales_order.total = subtotal + delivery_charge - (ecom_order.discount_amount or Decimal('0.00'))
    sales_order.save(update_fields=['subtotal', 'total'])

    ecom_order.sales_order = sales_order
    ecom_order.save(update_fields=['sales_order', 'customer'])

    return sales_order


# ── Coupon helpers ────────────────────────────────────────────────────────────

def validate_coupon(code, company, order_subtotal):
    from apps.ecom.models import DiscountCoupon
    try:
        coupon = DiscountCoupon.objects.get(code__iexact=code.strip(), company=company)
    except DiscountCoupon.DoesNotExist:
        return {'ok': False, 'error': 'Invalid coupon code.'}

    ok, error = coupon.is_valid(order_subtotal)
    if not ok:
        return {'ok': False, 'error': error}

    discount = coupon.compute_discount(order_subtotal)
    return {
        'ok': True,
        'coupon_id': str(coupon.id),
        'code': coupon.code,
        'discount_type': coupon.discount_type,
        'discount': float(discount),
        'final_total': float(Decimal(str(order_subtotal)) - discount),
    }


def apply_coupon_to_order(order, coupon):
    from django.db.models import F
    from apps.ecom.models import DiscountCoupon
    DiscountCoupon.objects.filter(pk=coupon.pk).update(uses_count=F('uses_count') + 1)


def notify_admin_new_order(ecom_order):
    """
    Send a new-order notification email to the store admin.
    Uses SiteSettings.contact_email; falls back to settings.ADMINS.
    Never raises — a mail failure must not break order placement.
    """
    try:
        from apps.ecom.models import SiteSettings
        site = SiteSettings.objects.filter(company=ecom_order.company).first()

        recipient = None
        if site and site.contact_email:
            recipient = site.contact_email
        elif getattr(settings, 'ADMINS', None):
            recipient = settings.ADMINS[0][1]

        if not recipient:
            logger.warning('notify_admin_new_order: no admin email configured for company %s', ecom_order.company_id)
            return

        items_lines = '\n'.join(
            f"  - {item.product.name} x{item.quantity}  Rs {item.total_price}"
            for item in ecom_order.items.select_related('product')
        )
        store_name = (site.store_name if site and site.store_name else 'Online Store')

        subject = f'[{store_name}] New Order {ecom_order.order_number} — Rs {ecom_order.total}'
        body = (
            f"A new order has been placed on {store_name}.\n\n"
            f"Order:    {ecom_order.order_number}\n"
            f"Customer: {ecom_order.customer_name}\n"
            f"Phone:    {ecom_order.customer_phone}\n"
            f"Address:  {ecom_order.delivery_address}\n"
            f"Payment:  {ecom_order.get_payment_method_display()}\n\n"
            f"Items:\n{items_lines}\n\n"
            f"Total:    Rs {ecom_order.total}\n"
        )
        if ecom_order.notes:
            body += f"\nCustomer note: {ecom_order.notes}\n"

        send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient],
            fail_silently=False,
        )
    except Exception:
        logger.exception('notify_admin_new_order failed for order %s', ecom_order.order_number)
