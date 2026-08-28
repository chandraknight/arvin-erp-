"""
Creates a SalesOrder (apps/orders) from an EcomOrder so the order
flows through order management, delivery, and POS.
"""
import logging
from decimal import Decimal
from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings

import nepali_datetime

from apps.company.models import Company, FiscalYear
from apps.orders.models import SalesOrder, SalesOrderItem
from apps.customers.models import Customer

logger = logging.getLogger(__name__)


def generate_ecom_order_number(company_id):
    """
    Format: {COMPANY_PREFIX}-EC-{FISCAL_YEAR}-{NNNN}, e.g. DPS-EC-2082/83-0001.
    Same fiscal-year-scoped, race-safe pattern as generate_invoice_number.
    Returns (order_number, sequence, fiscal_year).
    """
    from apps.ecom.models import EcomOrder

    today_np = nepali_datetime.date.today()
    fiscal_year = None
    try:
        company = Company.active_objects.get(id=company_id)
        company_prefix = company.name[:3].upper().strip().ljust(3, 'X')
        fiscal_year = FiscalYear.active_objects.filter(is_active=True, company=company).first()
        fiscal_year_name = fiscal_year.name if fiscal_year else today_np.strftime("%y/%m/%d")
    except (Company.DoesNotExist, AttributeError):
        company_prefix = "EC"
        fiscal_year_name = today_np.strftime("%y/%m/%d")

    prefix = f"{company_prefix}-EC-{fiscal_year_name}-"

    fy_filter = {'fiscal_year': fiscal_year} if fiscal_year else {'fiscal_year__isnull': True}
    with transaction.atomic():
        last_seq = EcomOrder.objects.select_for_update().filter(
            company_id=company_id,
            **fy_filter,
        ).aggregate(max_seq=Max('sequence_number'))

        sequence = (last_seq['max_seq'] or 0) + 1

        order_number = f"{prefix}{sequence:04d}"
        while EcomOrder.objects.filter(
            company_id=company_id, fiscal_year=fiscal_year, sequence_number=sequence
        ).exists() or EcomOrder.objects.filter(order_number=order_number).exists():
            sequence += 1
            order_number = f"{prefix}{sequence:04d}"

    return order_number, sequence, fiscal_year


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

    from apps.orders.services import generate_sales_order_number
    order_number, seq, fy = generate_sales_order_number(ecom_order.company.id)

    sales_order = SalesOrder(
        company=ecom_order.company,
        customer=customer,
        order_number=order_number,
        sequence_number=seq,
        fiscal_year=fy,
        order_date=timezone.now().date(),
        status='CONFIRMED',
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


# ── Payment / refund lifecycle ────────────────────────────────────────────────

def record_ecom_payment(ecom_order, user, bank_account=None):
    """
    Create a Payment for the full outstanding balance once COD cash is
    collected or an online payment is confirmed paid. Journalises via the
    existing apps/payments/signals.py receiver. Returns None (and logs a
    warning) if the order has no Invoice yet — payment confirmed before the
    order was ever moved to CONFIRMED is an edge case, not a crash.
    """
    from decimal import Decimal
    from apps.payments.models import Payment
    from apps.payments.services.payment_number_service import generate_payment_number

    order = ecom_order.sales_order
    invoice = order.invoice if order else None
    if not invoice:
        logger.warning(
            'record_ecom_payment: EcomOrder %s has no linked Invoice yet — skipping.',
            ecom_order.order_number,
        )
        return None

    if invoice.outstanding_balance <= Decimal('0.00'):
        return None

    method = 'CASH' if ecom_order.payment_method == 'COD' else 'BANK_TRANSFER'
    try:
        reference_number, _, pay_fy = generate_payment_number(ecom_order.company.id, 'CUSTOMER')
    except Exception:
        reference_number = None

    amount = invoice.outstanding_balance
    payment = Payment.objects.create(
        company=ecom_order.company,
        branch=order.branch,
        invoice=invoice,
        date=timezone.now().date(),
        amount=amount,
        amount_applied=amount,
        method=method,
        payment_type='CUSTOMER',
        bank_account=bank_account,
        reference_number=reference_number,
        fiscal_year=pay_fy,
        description=f'Ecom order {ecom_order.order_number} — {ecom_order.get_payment_method_display()}',
        created_by=user,
    )

    invoice.outstanding_balance = Decimal('0.00')
    invoice.save(update_fields=['outstanding_balance'])

    return payment


def refund_ecom_order(ecom_order, user):
    """
    Cancelling an order that was already paid needs a refund on the books.
    Creates a CreditNote for the paid amount — journalises via the existing
    apps/billing/signals.py create_journal_entry_for_credit_note receiver.
    Returns None if the order was never paid (nothing to refund).
    """
    from decimal import Decimal
    from apps.billing.models import CreditNote
    from apps.billing.services.note_service import generate_credit_note_number

    order = ecom_order.sales_order
    invoice = order.invoice if order else None
    if not invoice:
        return None

    was_paid = ecom_order.cod_status == 'COLLECTED' or ecom_order.payment_status == 'PAID'
    if not was_paid:
        return None

    if CreditNote.objects.filter(invoice=invoice, reason__icontains=ecom_order.order_number).exists():
        return None

    paid_amount = invoice.total - invoice.outstanding_balance
    if paid_amount <= Decimal('0.00'):
        return None

    number, seq, fy = generate_credit_note_number(ecom_order.company.id)
    credit_note = CreditNote.objects.create(
        company=ecom_order.company,
        invoice=invoice,
        customer=invoice.customer,
        credit_note_number=number,
        sequence_number=seq,
        fiscal_year=fy,
        amount=paid_amount,
        tax_amount=invoice.tax_amount,
        reason=f'Refund — order {ecom_order.order_number} cancelled after payment',
        created_by=user,
    )

    # A fully-paid invoice has outstanding_balance=0 — apply_credit_note()
    # would floor at 0 and lose the refund, so this flips it negative to
    # represent a credit owed back to the customer.
    invoice.outstanding_balance = invoice.outstanding_balance - credit_note.amount
    invoice.save(update_fields=['outstanding_balance'])

    from apps.utils.constant import StatusChoicesEnum
    credit_note.status = StatusChoicesEnum.Applied.value
    credit_note.save(update_fields=['status'])

    return credit_note


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


def send_newsletter(campaign):
    """
    Send a NewsletterCampaign to all active subscribers of its company via
    individual emails (send_mass_mail-style loop so one bad address doesn't
    abort the batch). Updates campaign.sent_at / recipient_count on success.
    Returns the number of subscribers the campaign was sent to (0 on failure).
    """
    from apps.ecom.models import NewsletterSubscriber

    subscribers = list(
        NewsletterSubscriber.objects.filter(company=campaign.company, is_active=True)
        .values_list('email', flat=True)
    )
    if not subscribers:
        return 0

    sent = 0
    for email in subscribers:
        try:
            send_mail(
                subject=campaign.subject,
                message=campaign.body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email],
                fail_silently=False,
            )
            sent += 1
        except Exception:
            logger.exception('send_newsletter: failed to send to %s (campaign %s)', email, campaign.pk)

    campaign.sent_at = timezone.now()
    campaign.recipient_count = sent
    campaign.save(update_fields=['sent_at', 'recipient_count'])
    return sent
