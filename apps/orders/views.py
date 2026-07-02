from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.db.models import Q, Sum
from django.http import HttpResponse
from django.views.decorators.http import require_POST
from decimal import Decimal

from apps.utils.mixins import AuthMixin
from apps.utils.htmx import is_htmx
from .models import SalesOrder, SalesOrderItem, DeliveryNote, DeliveryNoteItem, DeliveryTracking
from .forms import SalesOrderForm, SalesOrderItemFormSet, DeliveryNoteForm, DeliveryTrackingForm


def _require_orders(request):
    company = request.user_company
    if company and not company.enable_order_management:
        messages.warning(request, "Order management is not enabled for your company.")
        return redirect('accounts:user_dashboard')
    return None


# ── Dashboard ─────────────────────────────────────────────────────────────────

@login_required
def order_dashboard(request):
    guard = _require_orders(request)
    if guard:
        return guard

    company = request.user_company
    orders = SalesOrder.active_objects.filter(company=company)

    stats = {
        'total': orders.count(),
        'draft': orders.filter(status='DRAFT').count(),
        'confirmed': orders.filter(status='CONFIRMED').count(),
        'processing': orders.filter(status='PROCESSING').count(),
        'dispatched': orders.filter(status='DISPATCHED').count(),
        'delivered': orders.filter(status='DELIVERED').count(),
        'total_value': orders.aggregate(t=Sum('total'))['t'] or Decimal('0'),
    }

    pending_deliveries = DeliveryNote.active_objects.filter(
        company=company,
        status__in=['PENDING', 'PACKED', 'DISPATCHED', 'IN_TRANSIT', 'OUT_FOR_DELIVERY']
    ).select_related('sales_order').order_by('expected_delivery_date')[:10]

    recent_orders = orders.select_related('customer').order_by('-created_at')[:10]

    return render(request, 'orders/dashboard.html', {
        'stats': stats,
        'pending_deliveries': pending_deliveries,
        'recent_orders': recent_orders,
    })


# ── Sales Orders ──────────────────────────────────────────────────────────────

class SalesOrderListView(AuthMixin, ListView):
    model = SalesOrder
    template_name = 'orders/order_list.html'
    context_object_name = 'orders'
    permission_required = ['orders.view_salesorder']
    paginate_by = 20

    def get_queryset(self):
        qs = SalesOrder.active_objects.filter(
            company=self.request.user_company
        ).select_related('customer')
        # Branch isolation
        user_branch = getattr(self.request, 'user_branch', None)
        if user_branch is not None:
            qs = qs.filter(branch=user_branch)
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(order_number__icontains=q) |
                Q(customer__name__icontains=q)
            )
        status = self.request.GET.get('status', '').strip()
        if status:
            qs = qs.filter(status=status)
        return qs.order_by('-order_date')

    def get_template_names(self):
        if is_htmx(self.request):
            return ['orders/partials/order_table.html']
        return [self.template_name]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['q'] = self.request.GET.get('q', '')
        ctx['status'] = self.request.GET.get('status', '')
        return ctx


class SalesOrderDetailView(AuthMixin, DetailView):
    model = SalesOrder
    template_name = 'orders/order_detail.html'
    context_object_name = 'order'
    permission_required = ['orders.view_salesorder']

    def get_queryset(self):
        qs = SalesOrder.active_objects.filter(company=self.request.user_company)
        user_branch = getattr(self.request, 'user_branch', None)
        if user_branch is not None:
            qs = qs.filter(branch=user_branch)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['delivery_notes'] = self.object.delivery_notes.filter(
            is_deleted=False
        ).order_by('-dispatch_date')
        return ctx


class SalesOrderCreateView(AuthMixin, CreateView):
    model = SalesOrder
    form_class = SalesOrderForm
    template_name = 'orders/order_form.html'
    permission_required = ['orders.add_salesorder']

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw['request'] = self.request
        return kw

    def _formset(self, data=None):
        kwargs = {'form_kwargs': {'request': self.request}}
        if data:
            kwargs['data'] = data
        return SalesOrderItemFormSet(**kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['item_formset'] = self._formset(self.request.POST if self.request.POST else None)
        return ctx

    def form_valid(self, form):
        item_formset = self._formset(self.request.POST)
        if item_formset.is_valid():
            form.instance.company = self.request.user_company
            form.instance.created_by = self.request.user
            user_branch = getattr(self.request, 'user_branch', None)
            if user_branch is not None:
                form.instance.branch = user_branch
            from django.utils import timezone
            count = SalesOrder.objects.filter(company=self.request.user_company).count() + 1
            so_number = f"SO-{timezone.now().year}-{count:04d}"
            while SalesOrder.objects.filter(order_number=so_number).exists():
                count += 1
                so_number = f"SO-{timezone.now().year}-{count:04d}"
            form.instance.order_number = so_number
            self.object = form.save()
            item_formset.instance = self.object
            # Skip rows where product is blank (empty auto-added rows)
            instances = item_formset.save(commit=False)
            for item in instances:
                if item.product_id and item.unit_price is not None:
                    item.order = self.object
                    item.save()
            for obj in item_formset.deleted_objects:
                obj.delete()
            self._recalculate_totals(self.object)
            messages.success(self.request, f"Sales order {self.object.order_number} created.")
            return redirect('orders:order_detail', pk=self.object.pk)
        return self.form_invalid(form)

    def _recalculate_totals(self, order):
        items = order.items.filter(is_deleted=False)
        subtotal = sum(i.quantity * i.unit_price for i in items)
        discount = sum(i.quantity * i.unit_price * i.discount_percent / 100 for i in items)
        taxable = subtotal - discount
        tax = sum((i.quantity * i.unit_price - i.quantity * i.unit_price * i.discount_percent / 100)
                  * i.tax_percent / 100 for i in items)
        order.subtotal = subtotal
        order.discount_amount = discount
        order.tax_amount = tax
        delivery = order.delivery_charge or Decimal('0.00')
        order.total = taxable + tax + delivery
        order.save(update_fields=['subtotal', 'discount_amount', 'tax_amount', 'total'])


class SalesOrderUpdateView(AuthMixin, UpdateView):
    model = SalesOrder
    form_class = SalesOrderForm
    template_name = 'orders/order_form.html'
    permission_required = ['orders.change_salesorder']

    def get_queryset(self):
        qs = SalesOrder.active_objects.filter(
            company=self.request.user_company,
            status__in=['DRAFT', 'CONFIRMED']
        )
        user_branch = getattr(self.request, 'user_branch', None)
        if user_branch is not None:
            qs = qs.filter(branch=user_branch)
        return qs

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw['request'] = self.request
        return kw

    def _formset(self, data=None):
        kwargs = {'instance': self.object, 'form_kwargs': {'request': self.request}}
        if data:
            kwargs['data'] = data
        return SalesOrderItemFormSet(**kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['item_formset'] = self._formset(self.request.POST if self.request.POST else None)
        return ctx

    def get_success_url(self):
        return reverse_lazy('orders:order_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        item_formset = self._formset(self.request.POST)
        if item_formset.is_valid():
            form.instance.updated_by = self.request.user
            self.object = form.save()
            instances = item_formset.save(commit=False)
            for item in instances:
                if item.product_id and item.unit_price is not None:
                    item.order = self.object
                    item.save()
            for obj in item_formset.deleted_objects:
                obj.delete()
            self._recalculate_totals(self.object)
            messages.success(self.request, "Order updated.")
            return redirect(self.get_success_url())
        return self.form_invalid(form)

    def _recalculate_totals(self, order):
        items = order.items.filter(is_deleted=False)
        subtotal = sum(i.quantity * i.unit_price for i in items)
        discount = sum(i.quantity * i.unit_price * i.discount_percent / 100 for i in items)
        taxable = subtotal - discount
        tax = sum((i.quantity * i.unit_price - i.quantity * i.unit_price * i.discount_percent / 100)
                  * i.tax_percent / 100 for i in items)
        delivery = order.delivery_charge or Decimal('0.00')
        order.subtotal = subtotal
        order.discount_amount = discount
        order.tax_amount = tax
        order.total = taxable + tax + delivery
        order.save(update_fields=['subtotal', 'discount_amount', 'tax_amount', 'total'])


class SalesOrderDeleteView(AuthMixin, DeleteView):
    model = SalesOrder
    template_name = 'orders/confirm_delete.html'
    success_url = reverse_lazy('orders:order_list')
    permission_required = ['orders.delete_salesorder']

    def get_queryset(self):
        qs = SalesOrder.active_objects.filter(
            company=self.request.user_company, status='DRAFT'
        )
        user_branch = getattr(self.request, 'user_branch', None)
        if user_branch is not None:
            qs = qs.filter(branch=user_branch)
        return qs

    def form_valid(self, form):
        self.object.soft_delete(deleted_by=self.request.user)
        messages.success(self.request, "Order deleted.")
        return redirect(self.success_url)


@login_required
def confirm_order(request, pk):
    order = get_object_or_404(
        SalesOrder, pk=pk, company=request.user_company, status='DRAFT'
    )
    # Branch isolation
    user_branch = getattr(request, 'user_branch', None)
    if user_branch is not None and order.branch != user_branch:
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied('You do not have access to this order.')
    order.status = 'CONFIRMED'
    order.updated_by = request.user
    order.save(update_fields=['status', 'updated_by'])
    messages.success(request, f"Order {order.order_number} confirmed.")
    if is_htmx(request):
        resp = HttpResponse(status=204)
        resp['HX-Redirect'] = reverse_lazy('orders:order_detail', kwargs={'pk': pk})
        return resp
    return redirect('orders:order_detail', pk=pk)


@login_required
def cancel_order(request, pk):
    order = get_object_or_404(
        SalesOrder, pk=pk, company=request.user_company,
        status__in=['DRAFT', 'CONFIRMED', 'PROCESSING']
    )
    # Branch isolation
    user_branch = getattr(request, 'user_branch', None)
    if user_branch is not None and order.branch != user_branch:
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied('You do not have access to this order.')
    order.status = 'CANCELLED'
    order.updated_by = request.user
    order.save(update_fields=['status', 'updated_by'])
    messages.warning(request, f"Order {order.order_number} cancelled.")
    return redirect('orders:order_detail', pk=pk)


@login_required
def convert_to_invoice(request, pk):
    """Convert a confirmed/delivered sales order to an Invoice."""
    from apps.billing.models import Invoice, InvoiceItem
    from apps.company.services.company_services import setup_default_ledger_accounts
    from django.utils import timezone

    order = get_object_or_404(
        SalesOrder, pk=pk, company=request.user_company,
        status__in=['CONFIRMED', 'PROCESSING', 'DISPATCHED', 'DELIVERED']
    )

    # Branch isolation
    user_branch = getattr(request, 'user_branch', None)
    if user_branch is not None and order.branch != user_branch:
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied('You do not have access to this order.')

    if order.invoice:
        messages.info(request, "This order already has an invoice.")
        return redirect('billing:view_invoice_detail', pk=order.invoice.pk)

    setup_default_ledger_accounts(request.user_company)

    from apps.billing.services.invoice_service import generate_invoice_number
    is_vat = getattr(request.user_company, 'vat_registered', False)
    doc_type = 'INV' if is_vat else 'ORD'
    invoice_number, seq, fy = generate_invoice_number(request.user_company.id, doc_type=doc_type)

    invoice = Invoice.objects.create(
        company=request.user_company,
        customer=order.customer,
        branch=order.branch,
        transaction_date=timezone.now().date(),
        subtotal=order.subtotal,
        discount_amount=order.discount_amount,
        tax_amount=order.tax_amount,
        total=order.total,
        outstanding_balance=order.total,
        tax_percent=request.user_company.tax_rate,
        invoice_number=invoice_number,
        fiscal_year=fy,
        sequence_number=seq,
        status='ISSUED' if is_vat else 'ESTIMATE',
        created_by=request.user,
    )

    for item in order.items.filter(is_deleted=False):
        InvoiceItem.objects.create(
            invoice=invoice,
            product=item.product,
            description=item.description or (item.product.name if item.product else ''),
            quantity=int(item.quantity),
            price=item.unit_price,
            discount_percent=item.discount_percent,
        )

    order.invoice = invoice
    order.status = 'DELIVERED'
    order.save(update_fields=['invoice', 'status'])

    messages.success(request, f"Invoice created from order {order.order_number}.")
    return redirect('billing:view_invoice_detail', pk=invoice.pk)


# ── Delivery Notes ────────────────────────────────────────────────────────────

class DeliveryNoteListView(AuthMixin, ListView):
    model = DeliveryNote
    template_name = 'orders/delivery_list.html'
    context_object_name = 'deliveries'
    permission_required = ['orders.view_deliverynote']
    paginate_by = 20

    def get_queryset(self):
        qs = DeliveryNote.active_objects.filter(
            company=self.request.user_company
        ).select_related('sales_order')
        # Branch isolation — delivery notes inherit branch from their sales order
        user_branch = getattr(self.request, 'user_branch', None)
        if user_branch is not None:
            qs = qs.filter(sales_order__branch=user_branch)
        status = self.request.GET.get('status', '').strip()
        if status:
            qs = qs.filter(status=status)
        return qs.order_by('-dispatch_date')

    def get_context_data(self, **kwargs):
        from .models import DELIVERY_STATUS_CHOICES
        ctx = super().get_context_data(**kwargs)
        ctx['status'] = self.request.GET.get('status', '')
        ctx['statuses'] = DELIVERY_STATUS_CHOICES
        return ctx


class DeliveryNoteDetailView(AuthMixin, DetailView):
    model = DeliveryNote
    template_name = 'orders/delivery_detail.html'
    context_object_name = 'delivery'
    permission_required = ['orders.view_deliverynote']

    def get_queryset(self):
        qs = DeliveryNote.active_objects.filter(company=self.request.user_company)
        user_branch = getattr(self.request, 'user_branch', None)
        if user_branch is not None:
            qs = qs.filter(sales_order__branch=user_branch)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['tracking_events'] = self.object.tracking_events.filter(
            is_deleted=False
        ).order_by('-event_time')
        ctx['tracking_form'] = DeliveryTrackingForm()
        return ctx


class DeliveryNoteCreateView(AuthMixin, CreateView):
    model = DeliveryNote
    form_class = DeliveryNoteForm
    template_name = 'orders/delivery_form.html'
    permission_required = ['orders.add_deliverynote']

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw['request'] = self.request
        return kw

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['sales_order'] = get_object_or_404(
            SalesOrder, pk=self.kwargs['order_pk'], company=self.request.user_company
        )
        return ctx

    def form_valid(self, form):
        order = get_object_or_404(
            SalesOrder, pk=self.kwargs['order_pk'], company=self.request.user_company
        )
        form.instance.company = self.request.user_company
        form.instance.sales_order = order
        form.instance.created_by = self.request.user
        form.instance.delivery_address = form.instance.delivery_address or order.delivery_address
        form.instance.delivery_contact = form.instance.delivery_contact or order.delivery_contact
        form.instance.delivery_phone = form.instance.delivery_phone or order.delivery_phone

        # Auto-generate delivery number
        count = DeliveryNote.objects.filter(company=self.request.user_company).count() + 1
        from django.utils import timezone
        form.instance.delivery_number = f"DN-{timezone.now().year}-{count:04d}"

        self.object = form.save()

        # Create delivery items for all order items
        for item in order.items.filter(is_deleted=False):
            pending = item.quantity_pending
            if pending > 0:
                DeliveryNoteItem.objects.create(
                    delivery_note=self.object,
                    order_item=item,
                    quantity_delivered=pending,
                    created_by=self.request.user,
                )

        # Update order status
        order.status = 'DISPATCHED'
        order.save(update_fields=['status'])

        # Add initial tracking event
        DeliveryTracking.objects.create(
            delivery_note=self.object,
            status='DISPATCHED',
            notes='Delivery note created and dispatched.',
            updated_by_name=self.request.user.get_full_name() or self.request.user.email,
            created_by=self.request.user,
        )

        messages.success(self.request, f"Delivery note {self.object.delivery_number} created.")
        return redirect('orders:delivery_detail', pk=self.object.pk)


class DeliveryNoteUpdateView(AuthMixin, UpdateView):
    model = DeliveryNote
    form_class = DeliveryNoteForm
    template_name = 'orders/delivery_form.html'
    permission_required = ['orders.change_deliverynote']

    def get_queryset(self):
        qs = DeliveryNote.active_objects.filter(company=self.request.user_company)
        user_branch = getattr(self.request, 'user_branch', None)
        if user_branch is not None:
            qs = qs.filter(sales_order__branch=user_branch)
        return qs

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw['request'] = self.request
        return kw

    def get_success_url(self):
        return reverse_lazy('orders:delivery_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        messages.success(self.request, "Delivery note updated.")
        return super().form_valid(form)


@login_required
def mark_delivered(request, pk):
    delivery = get_object_or_404(
        DeliveryNote, pk=pk, company=request.user_company
    )
    # Branch isolation
    user_branch = getattr(request, 'user_branch', None)
    if user_branch is not None and delivery.sales_order.branch != user_branch:
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied('You do not have access to this delivery note.')
    from apps.utils.nepali_date import bs_str_to_ad
    from django.utils import timezone

    delivery.status = 'DELIVERED'
    delivery.actual_delivery_date = timezone.now().date()
    delivery.received_by = request.POST.get('received_by', '')
    delivery.updated_by = request.user
    delivery.save(update_fields=['status', 'actual_delivery_date', 'received_by', 'updated_by'])

    # Add tracking event
    DeliveryTracking.objects.create(
        delivery_note=delivery,
        status='DELIVERED',
        notes=f"Delivered. Received by: {delivery.received_by or 'N/A'}",
        updated_by_name=request.user.get_full_name() or request.user.email,
        created_by=request.user,
    )

    # Check if all deliveries for the order are complete
    order = delivery.sales_order
    all_delivered = not order.delivery_notes.filter(
        is_deleted=False
    ).exclude(status='DELIVERED').exists()
    if all_delivered:
        order.status = 'DELIVERED'
        order.save(update_fields=['status'])
        # Sync back to linked EcomOrder so storefront tracking shows correct status
        if hasattr(order, 'ecom_order') and order.ecom_order:
            order.ecom_order.status = 'DELIVERED'
            order.ecom_order.save(update_fields=['status'])

    messages.success(request, f"Delivery {delivery.delivery_number} marked as delivered.")
    return redirect('orders:delivery_detail', pk=pk)


@login_required
@require_POST
def cancel_delivery(request, pk):
    delivery = get_object_or_404(
        DeliveryNote, pk=pk, company=request.user_company,
        status__in=['PENDING', 'PACKED', 'DISPATCHED', 'IN_TRANSIT', 'OUT_FOR_DELIVERY', 'FAILED', 'RETURNED']
    )
    user_branch = getattr(request, 'user_branch', None)
    if user_branch is not None and delivery.sales_order.branch != user_branch:
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied('You do not have access to this delivery note.')

    delivery.status = 'CANCELLED'
    delivery.updated_by = request.user
    delivery.save(update_fields=['status', 'updated_by'])

    DeliveryTracking.objects.create(
        delivery_note=delivery,
        status='CANCELLED',
        notes=request.POST.get('reason', '').strip() or 'Delivery cancelled.',
        updated_by_name=request.user.get_full_name() or request.user.email,
        created_by=request.user,
    )

    messages.warning(request, f"Delivery {delivery.delivery_number} cancelled.")
    return redirect('orders:delivery_detail', pk=pk)


# ── Tracking ──────────────────────────────────────────────────────────────────

@login_required
def delivery_tracking_view(request, pk):
    delivery = get_object_or_404(DeliveryNote, pk=pk, company=request.user_company)
    # Branch isolation
    user_branch = getattr(request, 'user_branch', None)
    if user_branch is not None and delivery.sales_order.branch != user_branch:
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied('You do not have access to this delivery note.')
    events = delivery.tracking_events.filter(is_deleted=False).order_by('-event_time')
    return render(request, 'orders/delivery_tracking.html', {
        'delivery': delivery,
        'events': events,
        'form': DeliveryTrackingForm(),
    })


@login_required
def add_tracking_event(request, pk):
    delivery = get_object_or_404(DeliveryNote, pk=pk, company=request.user_company)
    # Branch isolation
    user_branch = getattr(request, 'user_branch', None)
    if user_branch is not None and delivery.sales_order.branch != user_branch:
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied('You do not have access to this delivery note.')
    if request.method == 'POST':
        form = DeliveryTrackingForm(request.POST)
        if form.is_valid():
            event = form.save(commit=False)
            event.delivery_note = delivery
            event.created_by = request.user
            if not event.updated_by_name:
                event.updated_by_name = request.user.get_full_name() or request.user.email
            event.save()

            # Update delivery status
            delivery.status = event.status
            delivery.updated_by = request.user
            delivery.save(update_fields=['status', 'updated_by'])

            messages.success(request, "Tracking event added.")
    return redirect('orders:delivery_track', pk=pk)


# ── HTMX ──────────────────────────────────────────────────────────────────────

@login_required
def htmx_order_items(request, order_pk):
    order = get_object_or_404(SalesOrder, pk=order_pk, company=request.user_company)
    # Branch isolation
    user_branch = getattr(request, 'user_branch', None)
    if user_branch is not None and order.branch != user_branch:
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied('You do not have access to this order.')
    return render(request, 'orders/partials/order_items.html', {'order': order})


# ── Print Receipt ─────────────────────────────────────────────────────────────

@login_required
def order_print_receipt(request, pk):
    guard = _require_orders(request)
    if guard:
        return guard
    order = get_object_or_404(SalesOrder, pk=pk, company=request.user_company)
    mode = request.GET.get('mode', 'a4')  # 'a4' or 'thermal'
    return render(request, 'orders/order_print_receipt.html', {
        'order': order,
        'company': request.user_company,
        'mode': mode,
    })
