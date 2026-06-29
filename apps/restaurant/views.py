"""
apps/restaurant/views.py
========================
All restaurant views — table floor plan, order management, KOT/BOT printing,
table transfer, and bill issuance.

All views are protected with @login_required or AuthMixin.
All querysets are scoped to request.user_company.
"""
import json
import logging
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import JsonResponse, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import CreateView, UpdateView, DeleteView, ListView
from django.urls import reverse_lazy

from apps.utils.decorator import auth_required
from apps.utils.mixins import AuthMixin
from .forms import (
    TableSectionForm, RestaurantTableForm, PrinterStationForm,
    DiningOrderForm, DiningOrderItemForm, TableTransferForm,
    MenuForm, MenuCategoryForm, MenuItemForm,
    RoomTypeForm, RoomForm, RoomBookingForm, RoomChargeForm,
)
from .models import (
    TableSection, RestaurantTable, PrinterStation,
    DiningOrder, DiningOrderItem, PrintJob,
    Menu, MenuCategory, MenuItem,
    RoomType, Room, RoomBooking, RoomCharge,
)
from .services.order_services import (
    open_order, add_item, print_kot, print_bot, issue_bill,
    transfer_table, close_order_paid,
    reprint_kot, reprint_bot, send_kot_and_bot,
    void_order, update_item_status,
)
from .services.menu_services import (
    get_published_menu, get_active_categories,
    publish_menu, unpublish_menu, toggle_item_availability,
)
from .services.room_services import (
    create_booking, check_in_room, check_out_room,
    add_room_charge, cancel_booking,
)

logger = logging.getLogger(__name__)


# ── Guard helper ──────────────────────────────────────────────────────────────

def _require_restaurant(request):
    """Redirect if restaurant module is not enabled for this company."""
    company = request.user_company
    if company and not company.enable_restaurant:
        messages.warning(request, "Restaurant module is not enabled for your company.")
        return redirect('accounts:user_dashboard')
    return None


def _get_order(request, pk):
    """Fetch a DiningOrder scoped to the user's company (and branch if set)."""
    qs = DiningOrder.active_objects.filter(company=request.user_company)
    user_branch = getattr(request, 'user_branch', None)
    if user_branch is not None:
        qs = qs.filter(branch=user_branch)
    return get_object_or_404(qs, pk=pk)


# ── Dashboard / Floor Plan ────────────────────────────────────────────────────

@login_required
def restaurant_dashboard(request):
    guard = _require_restaurant(request)
    if guard:
        return guard

    company = request.user_company
    sections = TableSection.active_objects.filter(company=company).prefetch_related(
        'tables__dining_orders'
    )
    # Tables without a section
    unsectioned = RestaurantTable.active_objects.filter(
        company=company, section__isnull=True, is_active=True
    )
    open_orders = DiningOrder.active_objects.filter(
        company=company, status__in=['OPEN', 'KOT_SENT', 'BOT_SENT', 'BILLED']
    ).select_related('table')

    return render(request, 'restaurant/dashboard.html', {
        'sections': sections,
        'unsectioned': unsectioned,
        'open_orders': open_orders,
        'open_count': open_orders.count(),
    })


# ── Table Management ──────────────────────────────────────────────────────────

class TableListView(AuthMixin, ListView):
    model = RestaurantTable
    template_name = 'restaurant/table_list.html'
    context_object_name = 'tables'
    permission_required = ['restaurant.view_restauranttable']

    def get_queryset(self):
        return RestaurantTable.active_objects.filter(
            company=self.request.user_company
        ).select_related('section').order_by('section__sort_order', 'table_number')


class TableCreateView(AuthMixin, CreateView):
    model = RestaurantTable
    form_class = RestaurantTableForm
    template_name = 'restaurant/table_form.html'
    permission_required = ['restaurant.add_restauranttable']
    success_url = reverse_lazy('restaurant:table_list')

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw['request'] = self.request
        return kw

    def form_valid(self, form):
        form.instance.company = self.request.user_company
        form.instance.created_by = self.request.user
        messages.success(self.request, "Table created.")
        return super().form_valid(form)


class TableUpdateView(AuthMixin, UpdateView):
    model = RestaurantTable
    form_class = RestaurantTableForm
    template_name = 'restaurant/table_form.html'
    permission_required = ['restaurant.change_restauranttable']
    success_url = reverse_lazy('restaurant:table_list')

    def get_queryset(self):
        return RestaurantTable.active_objects.filter(company=self.request.user_company)

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw['request'] = self.request
        return kw

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        messages.success(self.request, "Table updated.")
        return super().form_valid(form)


# ── Section Management ────────────────────────────────────────────────────────

class SectionCreateView(AuthMixin, CreateView):
    model = TableSection
    form_class = TableSectionForm
    template_name = 'restaurant/section_form.html'
    permission_required = ['restaurant.add_tablesection']
    success_url = reverse_lazy('restaurant:table_list')

    def form_valid(self, form):
        form.instance.company = self.request.user_company
        form.instance.created_by = self.request.user
        messages.success(self.request, "Section created.")
        return super().form_valid(form)


class SectionUpdateView(AuthMixin, UpdateView):
    model = TableSection
    form_class = TableSectionForm
    template_name = 'restaurant/section_form.html'
    permission_required = ['restaurant.change_tablesection']
    success_url = reverse_lazy('restaurant:table_list')

    def get_queryset(self):
        return TableSection.active_objects.filter(company=self.request.user_company)

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        messages.success(self.request, "Section updated.")
        return super().form_valid(form)


# ── Printer Stations ──────────────────────────────────────────────────────────

class PrinterListView(AuthMixin, ListView):
    model = PrinterStation
    template_name = 'restaurant/printer_list.html'
    context_object_name = 'printers'
    permission_required = ['restaurant.view_printerstation']

    def get_queryset(self):
        return PrinterStation.active_objects.filter(company=self.request.user_company)


class PrinterCreateView(AuthMixin, CreateView):
    model = PrinterStation
    form_class = PrinterStationForm
    template_name = 'restaurant/printer_form.html'
    permission_required = ['restaurant.add_printerstation']
    success_url = reverse_lazy('restaurant:printer_list')

    def form_valid(self, form):
        form.instance.company = self.request.user_company
        form.instance.created_by = self.request.user
        messages.success(self.request, "Printer station saved.")
        return super().form_valid(form)


class PrinterUpdateView(AuthMixin, UpdateView):
    model = PrinterStation
    form_class = PrinterStationForm
    template_name = 'restaurant/printer_form.html'
    permission_required = ['restaurant.change_printerstation']
    success_url = reverse_lazy('restaurant:printer_list')

    def get_queryset(self):
        return PrinterStation.active_objects.filter(company=self.request.user_company)

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        messages.success(self.request, "Printer station updated.")
        return super().form_valid(form)


# ── Dining Orders ─────────────────────────────────────────────────────────────

@auth_required('restaurant.add_diningorder')
def order_open(request, table_pk):
    """Open a new order on a table (GET shows form, POST creates order)."""
    guard = _require_restaurant(request)
    if guard:
        return guard

    table = get_object_or_404(
        RestaurantTable, pk=table_pk, company=request.user_company, is_active=True
    )

    if table.active_order:
        # Table already has an open order — redirect to it
        return redirect('restaurant:order_detail', pk=table.active_order.pk)

    if request.method == 'POST':
        form = DiningOrderForm(request.POST, request=request)
        if form.is_valid():
            order = open_order(
                request=request,
                table=table,
                covers=form.cleaned_data['covers'],
                waiter_name=form.cleaned_data.get('waiter_name', ''),
                customer=form.cleaned_data.get('customer'),
                notes=form.cleaned_data.get('notes', ''),
            )
            messages.success(request, f"Order {order.order_number} opened on {table.label}.")
            return redirect('restaurant:order_detail', pk=order.pk)
    else:
        form = DiningOrderForm(request=request, initial={'table': table})

    return render(request, 'restaurant/order_open.html', {'form': form, 'table': table})


@auth_required('restaurant.view_diningorder')
def order_detail(request, pk):
    """Main order screen — shows items, KOT/BOT buttons, add-item form."""
    guard = _require_restaurant(request)
    if guard:
        return guard

    order = _get_order(request, pk)
    item_form = DiningOrderItemForm(request=request)
    published_menu = get_published_menu(request.user_company)
    menu_categories = get_active_categories(published_menu) if published_menu else []

    return render(request, 'restaurant/order_detail.html', {
        'order': order,
        'item_form': item_form,
        'food_items': order.food_items,
        'beverage_items': order.beverage_items,
        'published_menu': published_menu,
        'menu_categories': menu_categories,
    })


@auth_required('restaurant.add_diningorderitem')
def order_add_item(request, pk):
    """HTMX POST — add an item to an open order, return updated item list partial."""
    guard = _require_restaurant(request)
    if guard:
        return guard

    order = _get_order(request, pk)

    if order.status in ('BILLED', 'PAID', 'CANCELLED'):
        return HttpResponse(
            '<p class="text-red-600 text-sm">Order is already closed.</p>', status=400
        )

    if request.method == 'POST':
        form = DiningOrderItemForm(request.POST, request=request)
        if form.is_valid():
            product = form.cleaned_data['product']
            unit_price = form.cleaned_data.get('unit_price') or product.price
            item_type = form.cleaned_data['item_type']

            # If the request came from the menu picker, use MenuItem price + type
            menu_item_id = request.POST.get('menu_item_id')
            if menu_item_id:
                menu_item = MenuItem.objects.filter(
                    pk=menu_item_id, category__menu__company=request.user_company
                ).select_related('category', 'product').first()
                if menu_item:
                    unit_price = menu_item.effective_price
                    raw_type = menu_item.category.item_type
                    item_type = 'FOOD' if raw_type in ('FOOD', 'BOTH') else 'BEVERAGE'

            item = add_item(
                order=order,
                product=product,
                quantity=form.cleaned_data['quantity'],
                item_type=item_type,
                unit_price=unit_price,
                discount_percent=form.cleaned_data.get('discount_percent', Decimal('0')),
                tax_percent=form.cleaned_data.get('tax_percent', Decimal('0')),
                notes=form.cleaned_data.get('notes', ''),
                created_by=request.user,
            )
            return render(request, 'restaurant/partials/order_items.html', {
                'order': order,
                'food_items': order.food_items,
                'beverage_items': order.beverage_items,
            })
        else:
            return render(request, 'restaurant/partials/item_form_errors.html', {'form': form})

    return HttpResponse(status=405)


@auth_required('restaurant.change_diningorderitem')
def order_remove_item(request, pk, item_pk):
    """Cancel a single item from an open order."""
    guard = _require_restaurant(request)
    if guard:
        return guard

    order = _get_order(request, pk)
    item = get_object_or_404(DiningOrderItem, pk=item_pk, order=order)

    if order.status in ('BILLED', 'PAID', 'CANCELLED'):
        raise PermissionDenied("Cannot modify a closed order.")

    item.status = 'CANCELLED'
    item.updated_by = request.user
    item.save(update_fields=['status', 'updated_by'])
    order.recalculate_totals()

    return render(request, 'restaurant/partials/order_items.html', {
        'order': order,
        'food_items': order.food_items,
        'beverage_items': order.beverage_items,
    })


# ── KOT / BOT ─────────────────────────────────────────────────────────────────

@auth_required('restaurant.add_printjob')
def print_kot_view(request, pk):
    """Send KOT to kitchen printer for all unprinted food items."""
    guard = _require_restaurant(request)
    if guard:
        return guard

    order = _get_order(request, pk)

    if request.method == 'POST':
        job = print_kot(order, request)
        if job:
            messages.success(request, f"KOT queued for {order.table.label}.")
        else:
            messages.info(request, "No new food items to send to kitchen.")
        if request.headers.get('HX-Request'):
            resp = HttpResponse(status=204)
            resp['HX-Trigger'] = json.dumps({
                'showToast': {
                    'level': 'success' if job else 'info',
                    'message': f"KOT {'queued' if job else 'nothing new'} for {order.table.label}.",
                }
            })
            return resp
        return redirect('restaurant:order_detail', pk=pk)

    return HttpResponse(status=405)


@auth_required('restaurant.add_printjob')
def print_bot_view(request, pk):
    """Send BOT to bar printer for all unprinted beverage items."""
    guard = _require_restaurant(request)
    if guard:
        return guard

    order = _get_order(request, pk)

    if request.method == 'POST':
        job = print_bot(order, request)
        if job:
            messages.success(request, f"BOT queued for {order.table.label}.")
        else:
            messages.info(request, "No new beverage items to send to bar.")
        if request.headers.get('HX-Request'):
            resp = HttpResponse(status=204)
            resp['HX-Trigger'] = json.dumps({
                'showToast': {
                    'level': 'success' if job else 'info',
                    'message': f"BOT {'queued' if job else 'nothing new'} for {order.table.label}.",
                }
            })
            return resp
        return redirect('restaurant:order_detail', pk=pk)

    return HttpResponse(status=405)


# ── Bill ──────────────────────────────────────────────────────────────────────

@auth_required('restaurant.change_diningorder')
def issue_bill_view(request, pk):
    """Convert the dining order to an Invoice and queue a bill print job."""
    guard = _require_restaurant(request)
    if guard:
        return guard

    order = _get_order(request, pk)

    if request.method == 'POST':
        try:
            invoice = issue_bill(order, request)
            messages.success(
                request,
                f"Bill issued — Invoice {invoice.invoice_number} created."
            )
            return redirect('billing:view_invoice_detail', pk=invoice.pk)
        except ValueError as e:
            messages.error(request, str(e))
            return redirect('restaurant:order_detail', pk=pk)

    return render(request, 'restaurant/confirm_bill.html', {'order': order})


# ── Table Transfer ────────────────────────────────────────────────────────────

@auth_required('restaurant.change_diningorder')
def table_transfer_view(request, pk):
    """Move an open order to a different (available) table."""
    guard = _require_restaurant(request)
    if guard:
        return guard

    order = _get_order(request, pk)

    if order.status in ('BILLED', 'PAID', 'CANCELLED'):
        messages.error(request, "Cannot transfer a closed order.")
        return redirect('restaurant:order_detail', pk=pk)

    if request.method == 'POST':
        form = TableTransferForm(
            request.POST,
            company=request.user_company,
            current_table=order.table,
        )
        if form.is_valid():
            target = form.cleaned_data['target_table']
            try:
                transfer_table(order, target, request)
                messages.success(
                    request,
                    f"Order {order.order_number} moved to {target.label}."
                )
            except ValueError as e:
                messages.error(request, str(e))
            return redirect('restaurant:order_detail', pk=pk)
    else:
        form = TableTransferForm(
            company=request.user_company,
            current_table=order.table,
        )

    return render(request, 'restaurant/table_transfer.html', {
        'order': order,
        'form': form,
    })


# ── Mark Table Available ──────────────────────────────────────────────────────

@auth_required('restaurant.change_restauranttable')
def table_set_available(request, table_pk):
    """Manually mark a table as AVAILABLE (after cleaning)."""
    guard = _require_restaurant(request)
    if guard:
        return guard

    table = get_object_or_404(
        RestaurantTable, pk=table_pk, company=request.user_company
    )
    if request.method == 'POST':
        active = table.active_order
        if active:
            messages.error(
                request,
                f"{table.label} still has open order {active.order_number}. "
                "Bill or void the order first."
            )
            return redirect('restaurant:order_detail', pk=active.pk)
        table.status = 'AVAILABLE'
        table.updated_by = request.user
        table.save(update_fields=['status', 'updated_by'])
        messages.success(request, f"{table.label} is now available.")
        return redirect('restaurant:dashboard')

    return render(request, 'restaurant/confirm_available.html', {'table': table})


# ── Print Job API (polled by local print agent) ───────────────────────────────

@login_required
def print_jobs_api(request):
    """
    JSON endpoint polled by the local print agent.
    Returns QUEUED jobs for this company and marks them SENT.
    """
    if not request.user_company:
        return JsonResponse({'jobs': []})

    jobs = PrintJob.objects.filter(
        company=request.user_company, status='QUEUED'
    ).select_related('printer')

    data = []
    for job in jobs:
        data.append({
            'id': str(job.pk),
            'type': job.job_type,
            'printer_ip': job.printer.ip_address if job.printer else None,
            'printer_port': job.printer.port if job.printer else 9100,
            'payload': job.payload,
        })

    # Mark as SENT
    from django.utils import timezone
    jobs.update(status='SENT', sent_at=timezone.now())

    return JsonResponse({'jobs': data})


@login_required
def print_job_fail(request, job_pk):
    """Local print agent reports a failed job."""
    if request.method == 'POST':
        job = get_object_or_404(PrintJob, pk=job_pk, company=request.user_company)
        job.status = 'FAILED'
        job.error_message = request.POST.get('error', 'Unknown error')
        job.save(update_fields=['status', 'error_message'])
        return JsonResponse({'ok': True})
    return JsonResponse({'ok': False}, status=405)


# ── Order List ────────────────────────────────────────────────────────────────

@auth_required('restaurant.view_diningorder')
def order_list(request):
    """List all dining orders for today with status filter."""
    guard = _require_restaurant(request)
    if guard:
        return guard

    from django.utils import timezone
    company = request.user_company
    qs = DiningOrder.active_objects.filter(company=company).select_related('table', 'customer')

    user_branch = getattr(request, 'user_branch', None)
    if user_branch is not None:
        qs = qs.filter(branch=user_branch)

    status = request.GET.get('status', '').strip()
    if status:
        qs = qs.filter(status=status)

    from apps.utils.nepali_date import bs_str_to_ad, ad_date_to_bs_str, today_bs

    date_str_bs = request.GET.get('date', today_bs())
    ad_date = bs_str_to_ad(date_str_bs)
    if ad_date:
        qs = qs.filter(opened_at__date=ad_date)
        filter_date_bs = date_str_bs
    else:
        filter_date_bs = today_bs()

    return render(request, 'restaurant/order_list.html', {
        'orders': qs.order_by('-opened_at'),
        'status': status,
        'filter_date_bs': filter_date_bs,
    })


# ── Reprint KOT / BOT ─────────────────────────────────────────────────────────

@auth_required('restaurant.add_printjob')
def reprint_kot_view(request, pk):
    """Force-reprint KOT for all food items (kitchen duplicate)."""
    guard = _require_restaurant(request)
    if guard:
        return guard

    order = _get_order(request, pk)
    if request.method == 'POST':
        job = reprint_kot(order, request)
        msg = f"KOT reprint queued for {order.table.label}." if job else "No food items to reprint."
        level = 'success' if job else 'info'
        if request.headers.get('HX-Request'):
            resp = HttpResponse(status=204)
            resp['HX-Trigger'] = json.dumps({'showToast': {'level': level, 'message': msg}})
            return resp
        getattr(messages, level)(request, msg)
        return redirect('restaurant:order_detail', pk=pk)
    return HttpResponse(status=405)


@auth_required('restaurant.add_printjob')
def reprint_bot_view(request, pk):
    """Force-reprint BOT for all beverage items (bar duplicate)."""
    guard = _require_restaurant(request)
    if guard:
        return guard

    order = _get_order(request, pk)
    if request.method == 'POST':
        job = reprint_bot(order, request)
        msg = f"BOT reprint queued for {order.table.label}." if job else "No beverage items to reprint."
        level = 'success' if job else 'info'
        if request.headers.get('HX-Request'):
            resp = HttpResponse(status=204)
            resp['HX-Trigger'] = json.dumps({'showToast': {'level': level, 'message': msg}})
            return resp
        getattr(messages, level)(request, msg)
        return redirect('restaurant:order_detail', pk=pk)
    return HttpResponse(status=405)


# ── Combined KOT + BOT ────────────────────────────────────────────────────────

@auth_required('restaurant.add_printjob')
def send_kot_bot_view(request, pk):
    """Send KOT and BOT together in one action."""
    guard = _require_restaurant(request)
    if guard:
        return guard

    order = _get_order(request, pk)
    if request.method == 'POST':
        kot_job, bot_job = send_kot_and_bot(order, request)
        sent = [t for t, j in [('KOT', kot_job), ('BOT', bot_job)] if j]
        msg = f"{' + '.join(sent)} queued for {order.table.label}." if sent else "Nothing new to send."
        level = 'success' if sent else 'info'
        if request.headers.get('HX-Request'):
            resp = HttpResponse(status=204)
            resp['HX-Trigger'] = json.dumps({'showToast': {'level': level, 'message': msg}})
            return resp
        getattr(messages, level)(request, msg)
        return redirect('restaurant:order_detail', pk=pk)
    return HttpResponse(status=405)


# ── Void Order ────────────────────────────────────────────────────────────────

@auth_required('restaurant.change_diningorder')
def void_order_view(request, pk):
    """Cancel an entire open order and free the table."""
    guard = _require_restaurant(request)
    if guard:
        return guard

    order = _get_order(request, pk)
    if order.status in ('BILLED', 'PAID', 'CANCELLED'):
        messages.error(request, f"Order is {order.status} and cannot be voided.")
        return redirect('restaurant:order_detail', pk=pk)

    if request.method == 'POST':
        reason = request.POST.get('reason', '').strip() or 'No reason given'
        try:
            void_order(order, reason, request)
            messages.success(request, f"Order {order.order_number} voided.")
            return redirect('restaurant:dashboard')
        except ValueError as e:
            messages.error(request, str(e))
            return redirect('restaurant:order_detail', pk=pk)

    return render(request, 'restaurant/confirm_void.html', {'order': order})


# ── Mark Order Paid ───────────────────────────────────────────────────────────

@auth_required('restaurant.change_diningorder')
def mark_order_paid_view(request, pk):
    """Mark a BILLED order as PAID (after cash/card payment collected)."""
    guard = _require_restaurant(request)
    if guard:
        return guard

    order = _get_order(request, pk)
    if request.method == 'POST':
        if order.status != 'BILLED':
            messages.error(request, f"Order must be BILLED before marking paid (currently {order.status}).")
            return redirect('restaurant:order_detail', pk=pk)
        close_order_paid(order, request)
        messages.success(request, f"Order {order.order_number} marked as paid. Table is now available.")
        return redirect('restaurant:dashboard')
    return render(request, 'restaurant/confirm_paid.html', {'order': order})


# ── Item Status Update (Kitchen/Bar staff) ────────────────────────────────────

@auth_required('restaurant.change_diningorderitem')
def item_status_update_view(request, pk, item_pk):
    """
    HTMX POST — advance a single item's status:
    PREPARING → READY  or  READY → SERVED
    """
    guard = _require_restaurant(request)
    if guard:
        return guard

    order = _get_order(request, pk)
    item = get_object_or_404(DiningOrderItem, pk=item_pk, order=order)

    if request.method == 'POST':
        new_status = request.POST.get('status', '').strip()
        try:
            update_item_status(item, new_status, request)
        except ValueError as e:
            if request.headers.get('HX-Request'):
                return HttpResponse(str(e), status=400)
            messages.error(request, str(e))
            return redirect('restaurant:order_detail', pk=pk)

        if request.headers.get('HX-Request'):
            return render(request, 'restaurant/partials/order_items.html', {
                'order': order,
                'food_items': order.food_items,
                'beverage_items': order.beverage_items,
            })
        return redirect('restaurant:order_detail', pk=pk)
    return HttpResponse(status=405)


# ── Print Job Dashboard (failed jobs + history) ───────────────────────────────

@auth_required('restaurant.view_printjob')
def print_job_dashboard(request):
    """Show print job history with failed jobs highlighted."""
    guard = _require_restaurant(request)
    if guard:
        return guard

    company = request.user_company
    jobs = (
        PrintJob.objects
        .filter(company=company)
        .select_related('printer', 'dining_order__table')
        .order_by('-created_at')[:200]
    )

    failed = [j for j in jobs if j.status == 'FAILED']
    queued = [j for j in jobs if j.status == 'QUEUED']

    return render(request, 'restaurant/print_job_dashboard.html', {
        'jobs': jobs,
        'failed_count': len(failed),
        'queued_count': len(queued),
    })


@auth_required('restaurant.change_printjob')
def retry_print_job(request, job_pk):
    """Re-queue a FAILED print job."""
    guard = _require_restaurant(request)
    if guard:
        return guard

    job = get_object_or_404(PrintJob, pk=job_pk, company=request.user_company)
    if request.method == 'POST':
        if job.status != 'FAILED':
            messages.error(request, "Only FAILED jobs can be retried.")
            return redirect('restaurant:print_job_dashboard')
        job.status = 'QUEUED'
        job.error_message = ''
        job.save(update_fields=['status', 'error_message'])
        messages.success(request, f"Job {job.pk} re-queued.")
        return redirect('restaurant:print_job_dashboard')
    return HttpResponse(status=405)


# ── Menu Management ───────────────────────────────────────────────────────────

@auth_required('restaurant.view_menu')
def menu_list(request):
    guard = _require_restaurant(request)
    if guard:
        return guard
    menus = Menu.active_objects.filter(company=request.user_company).prefetch_related('categories')
    return render(request, 'restaurant/menu_list.html', {'menus': menus})


@auth_required('restaurant.add_menu')
def menu_create(request):
    guard = _require_restaurant(request)
    if guard:
        return guard
    if request.method == 'POST':
        form = MenuForm(request.POST)
        if form.is_valid():
            menu = form.save(commit=False)
            menu.company = request.user_company
            menu.created_by = request.user
            menu.save()
            messages.success(request, f'Menu "{menu.name}" created.')
            return redirect('restaurant:menu_detail', pk=menu.pk)
    else:
        form = MenuForm()
    return render(request, 'restaurant/menu_form.html', {'form': form, 'title': 'Create Menu'})


@auth_required('restaurant.view_menu')
def menu_detail(request, pk):
    guard = _require_restaurant(request)
    if guard:
        return guard
    menu = get_object_or_404(Menu, pk=pk, company=request.user_company)
    categories = get_active_categories(menu)
    cat_form = MenuCategoryForm()
    item_form = MenuItemForm(company=request.user_company)
    return render(request, 'restaurant/menu_detail.html', {
        'menu': menu,
        'categories': categories,
        'cat_form': cat_form,
        'item_form': item_form,
    })


@auth_required('restaurant.change_menu')
def menu_edit(request, pk):
    guard = _require_restaurant(request)
    if guard:
        return guard
    menu = get_object_or_404(Menu, pk=pk, company=request.user_company)
    if request.method == 'POST':
        form = MenuForm(request.POST, instance=menu)
        if form.is_valid():
            form.instance.updated_by = request.user
            form.save()
            messages.success(request, 'Menu updated.')
            return redirect('restaurant:menu_detail', pk=menu.pk)
    else:
        form = MenuForm(instance=menu)
    return render(request, 'restaurant/menu_form.html', {'form': form, 'menu': menu, 'title': 'Edit Menu'})


@auth_required('restaurant.change_menu')
def menu_publish_toggle(request, pk):
    guard = _require_restaurant(request)
    if guard:
        return guard
    menu = get_object_or_404(Menu, pk=pk, company=request.user_company)
    if request.method == 'POST':
        if menu.is_published:
            unpublish_menu(menu, request.user)
            messages.info(request, f'"{menu.name}" unpublished.')
        else:
            publish_menu(menu, request.user)
            messages.success(request, f'"{menu.name}" is now the active published menu.')
        return redirect('restaurant:menu_list')
    return HttpResponse(status=405)


@auth_required('restaurant.add_menucategory')
def menu_category_add(request, menu_pk):
    guard = _require_restaurant(request)
    if guard:
        return guard
    menu = get_object_or_404(Menu, pk=menu_pk, company=request.user_company)
    if request.method == 'POST':
        form = MenuCategoryForm(request.POST)
        if form.is_valid():
            cat = form.save(commit=False)
            cat.menu = menu
            cat.created_by = request.user
            cat.save()
            if request.headers.get('HX-Request'):
                categories = get_active_categories(menu)
                return render(request, 'restaurant/partials/menu_category_list.html', {
                    'menu': menu, 'categories': categories,
                    'cat_form': MenuCategoryForm(),
                    'item_form': MenuItemForm(company=request.user_company),
                })
            messages.success(request, f'Category "{cat.name}" added.')
        else:
            messages.error(request, 'Fix form errors.')
    return redirect('restaurant:menu_detail', pk=menu_pk)


@auth_required('restaurant.add_menuitem')
def menu_item_add(request, menu_pk, category_pk):
    guard = _require_restaurant(request)
    if guard:
        return guard
    menu = get_object_or_404(Menu, pk=menu_pk, company=request.user_company)
    category = get_object_or_404(MenuCategory, pk=category_pk, menu=menu)
    if request.method == 'POST':
        form = MenuItemForm(request.POST, company=request.user_company)
        if form.is_valid():
            item = form.save(commit=False)
            item.category = category
            item.created_by = request.user
            item.save()
            if request.headers.get('HX-Request'):
                categories = get_active_categories(menu)
                return render(request, 'restaurant/partials/menu_category_list.html', {
                    'menu': menu, 'categories': categories,
                    'cat_form': MenuCategoryForm(),
                    'item_form': MenuItemForm(company=request.user_company),
                })
            messages.success(request, f'"{item.product.name}" added to {category.name}.')
        else:
            messages.error(request, 'Fix form errors.')
    return redirect('restaurant:menu_detail', pk=menu_pk)


@auth_required('restaurant.change_menuitem')
def menu_item_toggle(request, menu_pk, item_pk):
    guard = _require_restaurant(request)
    if guard:
        return guard
    menu = get_object_or_404(Menu, pk=menu_pk, company=request.user_company)
    item = get_object_or_404(MenuItem, pk=item_pk, category__menu=menu)
    if request.method == 'POST':
        toggle_item_availability(item, request.user)
        if request.headers.get('HX-Request'):
            categories = get_active_categories(menu)
            return render(request, 'restaurant/partials/menu_category_list.html', {
                'menu': menu, 'categories': categories,
                'cat_form': MenuCategoryForm(),
                'item_form': MenuItemForm(company=request.user_company),
            })
        return redirect('restaurant:menu_detail', pk=menu_pk)
    return HttpResponse(status=405)




# ── Room Management ───────────────────────────────────────────────────────────

@auth_required('restaurant.view_room')
def room_board(request):
    """Room status board — all rooms grouped by floor."""
    guard = _require_restaurant(request)
    if guard:
        return guard
    company = request.user_company
    rooms = Room.active_objects.filter(company=company).select_related(
        'room_type'
    ).prefetch_related('bookings').order_by('floor', 'room_number')
    return render(request, 'restaurant/room_board.html', {'rooms': rooms})


@auth_required('restaurant.view_roombooking')
def room_booking_list(request):
    guard = _require_restaurant(request)
    if guard:
        return guard
    company = request.user_company
    status = request.GET.get('status', '').strip()
    qs = RoomBooking.active_objects.filter(company=company).select_related('room', 'room__room_type')
    if status:
        qs = qs.filter(status=status)
    return render(request, 'restaurant/room_booking_list.html', {
        'bookings': qs.order_by('-check_in'),
        'status': status,
    })


@auth_required('restaurant.add_roombooking')
def room_booking_create(request):
    guard = _require_restaurant(request)
    if guard:
        return guard
    company = request.user_company
    if request.method == 'POST':
        form = RoomBookingForm(request.POST, company=company)
        if form.is_valid():
            d = form.cleaned_data
            try:
                booking = create_booking(
                    company=company,
                    room=d['room'],
                    guest_name=d['guest_name'],
                    guest_phone=d['guest_phone'],
                    guest_email=d.get('guest_email', ''),
                    check_in=d['check_in'],
                    check_out=d['check_out'],
                    adult_count=d.get('adult_count', 1),
                    child_count=d.get('child_count', 0),
                    notes=d.get('notes', ''),
                    created_by=request.user,
                )
                messages.success(request, f"Booking created for {booking.guest_name}.")
                return redirect('restaurant:room_booking_detail', pk=booking.pk)
            except ValueError as e:
                messages.error(request, str(e))
    else:
        room_pk = request.GET.get('room')
        initial = {'room': room_pk} if room_pk else {}
        form = RoomBookingForm(company=company, initial=initial)
    return render(request, 'restaurant/room_booking_form.html', {
        'form': form, 'title': 'New Room Booking',
    })


@auth_required('restaurant.view_roombooking')
def room_booking_detail(request, pk):
    guard = _require_restaurant(request)
    if guard:
        return guard
    booking = get_object_or_404(RoomBooking, pk=pk, company=request.user_company)
    charge_form = RoomChargeForm()
    return render(request, 'restaurant/room_booking_detail.html', {
        'booking': booking,
        'charges': booking.charges.all(),
        'charge_form': charge_form,
    })


@auth_required('restaurant.change_roombooking')
def room_check_in(request, pk):
    guard = _require_restaurant(request)
    if guard:
        return guard
    booking = get_object_or_404(RoomBooking, pk=pk, company=request.user_company)
    if request.method == 'POST':
        try:
            check_in_room(booking, user=request.user)
            messages.success(request, f"{booking.guest_name} checked in to Room {booking.room.room_number}.")
        except ValueError as e:
            messages.error(request, str(e))
        return redirect('restaurant:room_booking_detail', pk=pk)
    return render(request, 'restaurant/room_confirm_checkin.html', {'booking': booking})


@auth_required('restaurant.change_roombooking')
def room_check_out(request, pk):
    guard = _require_restaurant(request)
    if guard:
        return guard
    booking = get_object_or_404(RoomBooking, pk=pk, company=request.user_company)
    if request.method == 'POST':
        try:
            invoice = check_out_room(booking, user=request.user)
            messages.success(
                request,
                f"{booking.guest_name} checked out. Invoice {invoice.invoice_number} created."
            )
            return redirect('billing:view_invoice_detail', pk=invoice.pk)
        except ValueError as e:
            messages.error(request, str(e))
            return redirect('restaurant:room_booking_detail', pk=pk)
    return render(request, 'restaurant/room_confirm_checkout.html', {
        'booking': booking,
    })


@auth_required('restaurant.change_roombooking')
def room_add_charge(request, pk):
    guard = _require_restaurant(request)
    if guard:
        return guard
    booking = get_object_or_404(RoomBooking, pk=pk, company=request.user_company)
    if request.method == 'POST':
        form = RoomChargeForm(request.POST)
        if form.is_valid():
            try:
                add_room_charge(
                    booking=booking,
                    description=form.cleaned_data['description'],
                    amount=form.cleaned_data['amount'],
                    user=request.user,
                )
                messages.success(request, "Charge added.")
            except ValueError as e:
                messages.error(request, str(e))
        else:
            messages.error(request, "Invalid charge data.")
    return redirect('restaurant:room_booking_detail', pk=pk)


@auth_required('restaurant.change_roombooking')
def room_booking_cancel(request, pk):
    guard = _require_restaurant(request)
    if guard:
        return guard
    booking = get_object_or_404(RoomBooking, pk=pk, company=request.user_company)
    if request.method == 'POST':
        reason = request.POST.get('reason', '').strip() or 'No reason given'
        try:
            cancel_booking(booking, reason=reason, user=request.user)
            messages.success(request, f"Booking for {booking.guest_name} cancelled.")
            return redirect('restaurant:room_booking_list')
        except ValueError as e:
            messages.error(request, str(e))
            return redirect('restaurant:room_booking_detail', pk=pk)
    return render(request, 'restaurant/room_confirm_cancel.html', {'booking': booking})


# Room type + room CRUD

class RoomTypeListView(AuthMixin, ListView):
    model = RoomType
    template_name = 'restaurant/room_type_list.html'
    context_object_name = 'room_types'
    permission_required = ['restaurant.view_roomtype']

    def get_queryset(self):
        return RoomType.active_objects.filter(company=self.request.user_company)


class RoomTypeCreateView(AuthMixin, CreateView):
    model = RoomType
    form_class = RoomTypeForm
    template_name = 'restaurant/room_type_form.html'
    permission_required = ['restaurant.add_roomtype']
    success_url = reverse_lazy('restaurant:room_type_list')

    def form_valid(self, form):
        form.instance.company = self.request.user_company
        form.instance.created_by = self.request.user
        messages.success(self.request, "Room type created.")
        return super().form_valid(form)


class RoomTypeUpdateView(AuthMixin, UpdateView):
    model = RoomType
    form_class = RoomTypeForm
    template_name = 'restaurant/room_type_form.html'
    permission_required = ['restaurant.change_roomtype']
    success_url = reverse_lazy('restaurant:room_type_list')

    def get_queryset(self):
        return RoomType.active_objects.filter(company=self.request.user_company)

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        messages.success(self.request, "Room type updated.")
        return super().form_valid(form)


class RoomListView(AuthMixin, ListView):
    model = Room
    template_name = 'restaurant/room_list.html'
    context_object_name = 'rooms'
    permission_required = ['restaurant.view_room']

    def get_queryset(self):
        return Room.active_objects.filter(
            company=self.request.user_company
        ).select_related('room_type').order_by('floor', 'room_number')


class RoomCreateView(AuthMixin, CreateView):
    model = Room
    form_class = RoomForm
    template_name = 'restaurant/room_form.html'
    permission_required = ['restaurant.add_room']
    success_url = reverse_lazy('restaurant:room_list')

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw['company'] = self.request.user_company
        return kw

    def form_valid(self, form):
        form.instance.company = self.request.user_company
        form.instance.created_by = self.request.user
        messages.success(self.request, "Room created.")
        return super().form_valid(form)


class RoomUpdateView(AuthMixin, UpdateView):
    model = Room
    form_class = RoomForm
    template_name = 'restaurant/room_form.html'
    permission_required = ['restaurant.change_room']
    success_url = reverse_lazy('restaurant:room_list')

    def get_queryset(self):
        return Room.active_objects.filter(company=self.request.user_company)

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw['company'] = self.request.user_company
        return kw

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        messages.success(self.request, "Room updated.")
        return super().form_valid(form)


@auth_required('restaurant.change_room')
def room_set_available(request, pk):
    guard = _require_restaurant(request)
    if guard:
        return guard
    room = get_object_or_404(Room, pk=pk, company=request.user_company)
    if request.method == 'POST':
        active = room.active_booking
        if active:
            messages.error(request, f"Room {room.room_number} has an active booking ({active.guest_name}).")
            return redirect('restaurant:room_board')
        room.status = 'AVAILABLE'
        room.updated_by = request.user
        room.save(update_fields=['status', 'updated_by'])
        messages.success(request, f"Room {room.room_number} is now available.")
        return redirect('restaurant:room_board')
    return HttpResponse(status=405)
