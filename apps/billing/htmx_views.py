from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.views import View

from .forms import InvoiceItemFormSet, InvoiceItemForm
from apps.utils.constant import PAYMENT_METHOD_CHOICES


class InvoiceItemFormRowView(LoginRequiredMixin, View):
    """Return a fresh invoice item form row via HTMX.

    LoginRequiredMixin ensures unauthenticated requests are redirected to
    the login page rather than returning form HTML to anonymous users.
    """

    def get(self, request):
        form_index = int(request.GET.get('index', 0))
        form = InvoiceItemForm(prefix=f'items-{form_index}', request=request)
        company = getattr(request.user, 'company', None)
        org_type = company.organisation_type if company else 'TRADING'
        html = render_to_string(
            'billing/partials/invoice_item_row.html',
            {
                'item_form': form,
                'forloop': {'counter0': form_index, 'counter': form_index + 1},
                'org_type': org_type,
            },
            request=request,
        )
        return HttpResponse(html)


class InvoiceItemProductsView(LoginRequiredMixin, View):
    """Return filtered product/package options via HTMX.

    LoginRequiredMixin ensures unauthenticated requests are redirected to
    the login page.  Products and packages are additionally scoped to the
    user's company so cross-tenant data cannot be enumerated via this endpoint.
    """

    def get(self, request):
        from apps.products.models import Product, Package
        from apps.billing.models import CategoryType

        category_type_id = request.GET.get('category_type_id')
        products = []
        packages = []

        if category_type_id:
            try:
                # Scope the category lookup to the user's company (non-superusers)
                ct_qs = CategoryType.active_objects
                if not request.user.is_superuser and request.user.company:
                    ct_qs = ct_qs.filter(company=request.user.company)

                ct = ct_qs.get(id=category_type_id)

                product_qs = Product.active_objects.filter(category_type=ct)
                package_qs = Package.active_objects.filter(category_type=ct)

                # Further scope to company for non-superusers
                if not request.user.is_superuser and request.user.company:
                    product_qs = product_qs.filter(company=request.user.company)
                    package_qs = package_qs.filter(company=request.user.company)

                products = product_qs.values('id', 'name')
                packages = package_qs.values('id', 'name')
            except CategoryType.DoesNotExist:
                pass

        html = render_to_string(
            'billing/partials/item_product_options.html',
            {'products': products, 'packages': packages},
            request=request,
        )
        return HttpResponse(html)


class CollectPaymentHtmxView(LoginRequiredMixin, View):
    """HTMX view for collecting a payment against an existing invoice.

    GET  → renders the payment modal form partial.
    POST → processes the payment and returns a success/error partial.

    Security:
    - LoginRequiredMixin blocks unauthenticated requests.
    - Invoice is fetched with company scoping for non-superusers (§2.3).
    - CSRF is enforced by Django's CsrfViewMiddleware (no @csrf_exempt).
    """

    def _get_invoice(self, request, pk):
        """Return the invoice, scoped to the user's company for non-superusers."""
        from apps.billing.models import Invoice
        if request.user.is_superuser:
            return get_object_or_404(Invoice, pk=pk)
        return get_object_or_404(Invoice, pk=pk, company=request.user_company)

    def get(self, request, pk):
        from apps.utils.nepali_date import today_bs
        invoice = self._get_invoice(request, pk)
        html = render_to_string(
            'billing/partials/collect_payment_modal.html',
            {
                'invoice': invoice,
                'payment_methods': PAYMENT_METHOD_CHOICES,
                'today_bs': today_bs(),
            },
            request=request,
        )
        return HttpResponse(html)

    def post(self, request, pk):
        import logging
        from decimal import Decimal, InvalidOperation
        from apps.billing.models import Invoice
        from apps.payments.services.payment_services import create_invoice_payment
        from apps.utils.nepali_date import NepaliDateField

        logger = logging.getLogger(__name__)
        audit_logger = logging.getLogger('audit')

        invoice = self._get_invoice(request, pk)

        # --- Parse and validate inputs ---
        payment_reference = request.POST.get('payment_reference', '').strip() or None
        payment_description = request.POST.get('payment_description', '').strip() or None
        payment_date_bs = request.POST.get('payment_date', '').strip() or None

        errors = []
        valid_methods = [m[0] for m in PAYMENT_METHOD_CHOICES]

        # Build list of (method, amount) — primary row + any split rows
        payment_rows = []

        primary_method = request.POST.get('payment_method', '').strip()
        primary_amount_raw = request.POST.get('payment_amount', '').strip()

        if not primary_method or primary_method not in valid_methods:
            errors.append("A valid payment method is required.")
        if not primary_amount_raw:
            errors.append("Payment amount is required.")
        else:
            try:
                amt = Decimal(primary_amount_raw)
                if amt <= 0:
                    errors.append("Payment amount must be greater than zero.")
                else:
                    payment_rows.append((primary_method, amt))
            except InvalidOperation:
                errors.append("Payment amount must be a valid number.")

        # Parse split rows
        extra_methods = request.POST.getlist('extra_payment_method')
        extra_amounts = request.POST.getlist('extra_payment_amount')
        for idx, (method, raw) in enumerate(zip(extra_methods, extra_amounts), start=2):
            method = method.strip()
            if not method or method not in valid_methods:
                errors.append(f"Row {idx}: select a valid payment method.")
                continue
            try:
                amt = Decimal(raw)
                if amt <= 0:
                    errors.append(f"Row {idx}: amount must be greater than zero.")
                else:
                    payment_rows.append((method, amt))
            except InvalidOperation:
                errors.append(f"Row {idx}: invalid amount.")

        # Validate total does not exceed outstanding
        if not errors:
            total_split = sum(a for _, a in payment_rows)
            if total_split > invoice.outstanding_balance:
                errors.append(
                    f"Total split amount ({total_split}) exceeds outstanding balance "
                    f"({invoice.outstanding_balance})."
                )

        # Convert BS date to AD if provided
        payment_date = None
        if payment_date_bs:
            try:
                import nepali_datetime
                np_date = nepali_datetime.datetime.strptime(payment_date_bs, '%Y-%m-%d')
                payment_date = np_date.to_datetime_date()
            except (ValueError, AttributeError):
                errors.append("Invalid payment date format. Use YYYY-MM-DD (BS).")

        if errors:
            from apps.utils.nepali_date import today_bs
            html = render_to_string(
                'billing/partials/collect_payment_modal.html',
                {
                    'invoice': invoice,
                    'payment_methods': PAYMENT_METHOD_CHOICES,
                    'errors': errors,
                    'form_data': request.POST,
                    'today_bs': today_bs(),
                },
                request=request,
            )
            return HttpResponse(html)

        # --- Create one payment per row ---
        created_payments = []
        for method, amount in payment_rows:
            success, payment_obj, error = create_invoice_payment(
                request=request,
                invoice=invoice,
                payment_method=method,
                payment_amount=amount,
                payment_reference=payment_reference,
                payment_description=payment_description,
                payment_date=payment_date,
            )
            if not success:
                html = render_to_string(
                    'billing/partials/collect_payment_modal.html',
                    {
                        'invoice': invoice,
                        'payment_methods': PAYMENT_METHOD_CHOICES,
                        'errors': [error],
                        'form_data': request.POST,
                    },
                    request=request,
                )
                return HttpResponse(html)
            created_payments.append(payment_obj)
            invoice.refresh_from_db()

        if len(created_payments) > 1:
            from apps.payments.services.payment_services import consolidate_split_payment_journals
            consolidate_split_payment_journals(created_payments)

        payment = created_payments[-1] if created_payments else None

        # Refresh invoice from DB so outstanding_balance is current
        invoice.refresh_from_db()

        audit_logger.info(
            'COLLECT_PAYMENT_HTMX invoice=%s payment=%s amount=%s actor=%s company=%s',
            invoice.invoice_number, payment.id, payment.amount,
            request.user.email, getattr(request, 'user_company', None) or invoice.company,
        )

        html = render_to_string(
            'billing/partials/collect_payment_success.html',
            {
                'invoice': invoice,
                'payment': payment,
            },
            request=request,
        )
        return HttpResponse(html)
