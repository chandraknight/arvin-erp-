from .forms import PurchaseOrderForm, PurchaseOrderItemFormSet, VendorBillForm, VendorBillItemForm, VendorPaymentForm
from ..utils.global_models import *
from .view_collections.all_views import *

import logging
from django.contrib import messages
from django.shortcuts import redirect

logger = logging.getLogger(__name__)


def _purchasing_enabled(request):
    """Return True if purchasing module is enabled for the current company."""
    if request.user.is_superuser:
        return True
    company = getattr(request, 'user_company', None) or getattr(request.user, 'company', None)
    return bool(company and getattr(company, 'enable_purchasing', False))


def _purchasing_guard(request):
    """Redirect with warning if purchasing is disabled; return None if allowed."""
    if not _purchasing_enabled(request):
        messages.warning(request, "Purchasing module is not enabled for your company.")
        return redirect('accounts:user_dashboard')
    return None


@login_required
def purchase_order_list(request):
    guard = _purchasing_guard(request)
    if guard:
        return guard
    if request.user.is_superuser:
        purchase_orders = PurchaseOrder.objects.all().order_by('-date', '-created_at')
    else:
        purchase_orders = PurchaseOrder.objects.select_related('vendor').filter(
            vendor__company=request.user.company
        ).order_by('-date', '-created_at')
        user_branch = getattr(request, 'user_branch', None)
        if user_branch is not None:
            purchase_orders = purchase_orders.filter(branch=user_branch)
    return render(request, 'purchasing/purchase_order_list.html', {'purchase_orders': purchase_orders})


@login_required
def purchase_order_detail(request, pk):
    guard = _purchasing_guard(request)
    if guard:
        return guard
    if request.user.is_superuser:
        purchase_order = get_object_or_404(
            PurchaseOrder.objects.prefetch_related('items__product'), pk=pk
        )
    else:
        purchase_order = get_object_or_404(
            PurchaseOrder.objects.prefetch_related('items__product'),
            pk=pk, vendor__company=request.user.company
        )
        # Branch isolation — a branch-assigned user may only view their branch's POs
        user_branch = getattr(request, 'user_branch', None)
        if user_branch is not None and purchase_order.branch != user_branch:
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied('You do not have access to this purchase order.')
    return render(request, 'purchasing/purchase_order_detail.html', {'purchase_order': purchase_order})

@login_required
def receive_purchase_order(request, pk):
    guard = _purchasing_guard(request)
    if guard:
        return guard
    if request.user.is_superuser:
        purchase_order = get_object_or_404(PurchaseOrder, pk=pk)
    else:
        from django.db.models import Q
        # Accept both new-style (direct company FK) and legacy (via vendor.company)
        purchase_order = get_object_or_404(
            PurchaseOrder,
            Q(company=request.user.company) | Q(vendor__company=request.user.company),
            pk=pk,
        )
        # Branch isolation — only the owning branch can receive a PO
        user_branch = getattr(request, 'user_branch', None)
        if user_branch is not None and purchase_order.branch != user_branch:
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied('You do not have access to this purchase order.')

    # Prevent receiving if already received or cancelled
    if purchase_order.status in ['RECEIVED', 'CANCELLED']:
        messages.warning(request, f"Purchase Order {purchase_order.purchase_order_number} cannot be received as its status is {purchase_order.status}.")
        return redirect('purchasing:purchase_order_detail', pk=pk)

    if request.method == 'POST':
        with transaction.atomic():
            try:
                # Update PO status
                purchase_order.status = 'RECEIVED'
                purchase_order.save()

                # Only update inventory if the company has inventory enabled
                company = purchase_order.company or purchase_order.vendor.company
                if company and company.enable_inventory:
                    from decimal import Decimal
                    for item in purchase_order.items.filter(item_type='STOCK'):
                        if item.product:
                            factor = Decimal(str(item.product.conversion_factor or 1))
                            # Convert purchase units → sale units (e.g. 5 KG → 5000 gram, 3 packs of 12 → 36 pcs)
                            sale_qty = int(Decimal(str(item.quantity)) * factor)
                            ProductStock.objects.get_or_create(product=item.product)
                            # select_for_update + F() prevents duplicate stock from concurrent receives
                            ProductStock.objects.select_for_update().filter(
                                product=item.product
                            ).update(stock=F('stock') + sale_qty)

                            StockTransaction.objects.create(
                                product=item.product,
                                user=request.user,
                                transaction_type='ADD',
                                quantity=sale_qty,
                                reason=f'PO received: {purchase_order.purchase_order_number}',
                            )

                            if item.price and item.price > 0:
                                item.product.cost_price = item.price
                                item.product.save(update_fields=['cost_price'])

                messages.success(request, f"Purchase Order {purchase_order.purchase_order_number} marked as received and inventory updated.")
                return redirect('purchasing:purchase_order_detail', pk=pk)

            except Exception as e:
                logger.error(f"Error receiving purchase order {purchase_order.purchase_order_number}: {e}")
                messages.error(request, f"An error occurred while receiving the purchase order: {e}")
                raise # Trigger transaction rollback

    # If not POST, just redirect to detail view (or show a confirmation page if needed)
    return redirect('purchasing:purchase_order_detail', pk=pk)

@login_required
def vendor_bill_list(request):
    guard = _purchasing_guard(request)
    if guard:
        return guard
    if request.user.is_superuser:
        vendor_bills = VendorBill.objects.all().order_by('-bill_date', '-created_at')
    else:
        vendor_bills = VendorBill.objects.select_related('vendor').filter(
            vendor__company=request.user.company
        ).order_by('-bill_date', '-created_at')
        user_branch = getattr(request, 'user_branch', None)
        if user_branch is not None:
            vendor_bills = vendor_bills.filter(branch=user_branch)
    from datetime import date
    return render(request, 'purchasing/vendor_bill_list.html', {
        'vendor_bills': vendor_bills,
        'today': date.today(),
        'rupee': RUPEE,
    })

@login_required
def vendor_bill_create(request):
    guard = _purchasing_guard(request)
    if guard:
        return guard
    from .forms import vendor_bill_item_formset_factory
    company = getattr(request.user, 'company', None)
    ScopedFormSet = vendor_bill_item_formset_factory(company)

    if request.method == 'POST':
        form = VendorBillForm(request.POST, request=request)
        formset = ScopedFormSet(request.POST, instance=VendorBill())

        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                try:
                    vendor_bill = form.save(commit=False)
                    if request.user.is_authenticated:
                        vendor_bill.created_by = request.user
                    if not request.user.is_superuser and hasattr(request.user, 'company'):
                        vendor_bill.company = request.user.company
                    user_branch = getattr(request, 'user_branch', None)
                    if user_branch is not None:
                        vendor_bill.branch = user_branch
                    # Skip journaling here — items not yet saved, total is 0
                    vendor_bill._skip_journal = True
                    vendor_bill.save()

                    # Auto-assign debit_account (Purchases/expense) since removed from UI
                    from apps.bookkeeping.models import LedgerAccount
                    default_account = None
                    if company:
                        default_account = (
                            LedgerAccount.objects.filter(company=company, name='Purchases', account_type='EXPENSE').first()
                            or LedgerAccount.objects.filter(company=company, account_type='EXPENSE', is_deleted=False).first()
                        )

                    items = formset.save(commit=False)
                    for item in items:
                        item.vendor_bill = vendor_bill
                        if not getattr(item, 'debit_account_id', None) and default_account:
                            item.debit_account = default_account
                        item.save()
                    for obj in formset.deleted_objects:
                        obj.delete()

                    from decimal import Decimal
                    tax_percent = form.cleaned_data.get('tax_percent') or Decimal('0.00')
                    vendor_bill.tax_percent = tax_percent
                    # Don't save yet — update_vendor_bill_total will compute tax_amount
                    # and save both tax_percent + total_amount + tax_amount together
                    # to avoid a spurious zero-VAT journal being posted here.

                    from apps.billing.services.vendor_bill_service import update_vendor_bill_total
                    update_vendor_bill_total(vendor_bill)  # saves tax_percent, tax_amount, total_amount

                    # Record payment if requested
                    collect = form.cleaned_data.get('collect_payment', False)
                    if collect:
                        from apps.payments.models import VendorPayment
                        from apps.utils.constant import PAYMENT_METHOD_CHOICES
                        from decimal import Decimal as D
                        from django.utils import timezone as tz

                        valid_methods = [m[0] for m in PAYMENT_METHOD_CHOICES]
                        payment_date_ad = form.cleaned_data.get('payment_date') or tz.now().date()
                        payment_rows = []

                        primary_method = form.cleaned_data.get('payment_method')
                        primary_amount = form.cleaned_data.get('payment_amount')
                        if primary_method and primary_amount and primary_amount > 0:
                            payment_rows.append((primary_method, primary_amount))

                        for method, raw in zip(
                            request.POST.getlist('extra_payment_method'),
                            request.POST.getlist('extra_payment_amount'),
                        ):
                            method = method.strip()
                            if method not in valid_methods:
                                continue
                            try:
                                amt = D(raw)
                                if amt > 0:
                                    payment_rows.append((method, amt))
                            except Exception:
                                pass

                        if payment_rows:
                            for method, amount in payment_rows:
                                VendorPayment.objects.create(
                                    vendor_bill=vendor_bill,
                                    amount=amount,
                                    payment_date=payment_date_ad,
                                    payment_method=method,
                                    created_by=request.user,
                                )
                            vendor_bill.status = 'PAID'
                            vendor_bill.save(update_fields=['status'])
                            total_paid = sum(a for _, a in payment_rows)
                            messages.success(request, f"Vendor Bill created and payment of ₹{total_paid} recorded.")
                        else:
                            messages.success(request, "Vendor Bill created successfully.")
                    else:
                        messages.success(request, "Vendor Bill created successfully.")

                    return redirect('purchasing:purchase_dashboard')

                except Exception as e:
                    logger.error(f"Error creating vendor bill: {e}")
                    messages.error(request, f"An error occurred while creating the vendor bill: {e}")
                    raise
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = VendorBillForm(request=request)
        formset = ScopedFormSet(instance=VendorBill())

    return render(request, 'purchasing/vendor_bill_create.html', {
        'form': form,
        'formset': formset,
        'tax_rate': company.tax_rate if company else 0,
    })

@login_required
def vendor_payment_list(request):
    guard = _purchasing_guard(request)
    if guard:
        return guard
    if request.user.is_superuser:
        vendor_payments = VendorPayment.objects.all().order_by('-payment_date', '-created_at')
    else:
        vendor_payments = VendorPayment.objects.filter(
            vendor_bill__company=request.user.company
        ).order_by('-payment_date', '-created_at')
    return render(request, 'purchasing/vendor_payment_list.html', {
        'vendor_payments': vendor_payments,
        'rupee': RUPEE,
    })

@login_required
def vendor_payment_create(request):
    guard = _purchasing_guard(request)
    if guard:
        return guard
    if request.method == 'POST':
        form = VendorPaymentForm(request.POST, request=request)
        if form.is_valid():
            try:
                vendor_payment = form.save(commit=False)
                if request.user.is_authenticated:
                    vendor_payment.created_by = request.user
                vendor_payment.save()
                messages.success(request, "Vendor Payment recorded successfully.")
                return redirect('reports:vendor_payment_list_report')
            except Exception as e:
                logger.error(f"Error creating vendor payment: {e}")
                messages.error(request, f"An error occurred while recording the vendor payment: {e}")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = VendorPaymentForm(request=request)
    return render(request, 'purchasing/vendor_payment_create.html', {'form': form})


@login_required
def htmx_vendor_bill_summary(request):
    from django.http import HttpResponse
    from apps.billing.models import VendorBill
    bill_id = request.GET.get('bill_id', '').strip()
    if not bill_id:
        return HttpResponse('<p class="text-sm text-gray-400 italic">Select a vendor bill to see details.</p>')
    try:
        qs = VendorBill.objects.select_related('vendor').prefetch_related('payments')
        if not request.user.is_superuser:
            qs = qs.filter(vendor__company=request.user.company)
        bill = qs.get(pk=bill_id)
    except VendorBill.DoesNotExist:
        return HttpResponse('<p class="text-sm text-red-500">Bill not found.</p>')
    paid = sum(p.amount for p in bill.payments.all())
    balance = bill.total_amount - paid
    return render(request, 'purchasing/partials/vendor_bill_summary_panel.html', {
        'bill': bill, 'paid': paid, 'balance': balance,
    })


@login_required
def htmx_vendor_bill_item_form(request):
    """Return a single blank vendor bill item row for HTMX insertion."""
    from django.template.loader import render_to_string
    from django.http import HttpResponse
    form_index = int(request.GET.get('index', 0))
    company = getattr(request.user, 'company', None)
    form = VendorBillItemForm(prefix=f'items-{form_index}', company=company)
    html = render_to_string(
        'purchasing/partials/vendor_bill_item_row.html',
        {'item_form': form, 'forloop': {'counter0': form_index}},
        request=request,
    )
    return HttpResponse(html)


@auth_required('purchasing.view_purchaseorder', 'purchasing.view_purchaseorderitem')
def purchase_order_dashboard(request):
    guard = _purchasing_guard(request)
    if guard:
        return guard
    from django.db.models import Q
    from apps.utils.htmx import is_htmx

    user_company = request.user.company

    items_prefetch = Prefetch(
        'items',
        queryset=PurchaseOrderItem.active_objects.select_related('product').filter(
            product__company=user_company
        )
    )

    purchase_orders = PurchaseOrder.active_objects.filter(
        vendor__company=user_company
    ).prefetch_related(items_prefetch).select_related('vendor').order_by('-date')

    # Live search
    q = request.GET.get('q', '').strip()
    if q:
        purchase_orders = purchase_orders.filter(
            Q(purchase_order_number__icontains=q) |
            Q(vendor__name__icontains=q)
        )

    # Status filter
    status = request.GET.get('status', '').strip()
    if status:
        purchase_orders = purchase_orders.filter(status=status)

    total_po_amount = purchase_orders.aggregate(Sum('total_amount'))['total_amount__sum'] or 0

    paginator = Paginator(purchase_orders, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'object_list': page_obj.object_list,
        'page_obj': page_obj,
        'total_po_amount': total_po_amount,
        'rupee': RUPEE,
        'q': q,
        'status': status,
    }

    if is_htmx(request):
        return render(request, 'purchasing/partials/po_table.html', context)

    return render(request, 'purchasing/purchase_order_dashboard.html', context)


@auth_required('purchasing.view_purchaseorder')
def purchasing_hub(request):
    guard = _purchasing_guard(request)
    if guard:
        return guard
    """
    Purchasing landing page — mirrors billing_dashboard for the procurement side.
    Shows PO stats, vendor bill summary, recent activity, quick actions.
    """
    from django.db.models import Q, Sum, Count
    from apps.utils.htmx import is_htmx
    from datetime import date
    from decimal import Decimal

    company = request.user_company
    user_branch = getattr(request, 'user_branch', None)

    po_qs = PurchaseOrder.active_objects.filter(company=company)
    if user_branch:
        po_qs = po_qs.filter(branch=user_branch)

    bill_qs = VendorBill.objects.filter(vendor__company=company)
    if user_branch:
        bill_qs = bill_qs.filter(branch=user_branch)

    today = date.today()
    month_start = today.replace(day=1)

    po_stats = po_qs.aggregate(
        count_draft=Count('id', filter=Q(status='DRAFT')),
        count_sent=Count('id', filter=Q(status='SENT')),
        count_received=Count('id', filter=Q(status='RECEIVED')),
        total_pending_value=Sum('total_amount', filter=Q(status__in=['DRAFT', 'SENT'])),
        total_received_month=Sum(
            'total_amount',
            filter=Q(status='RECEIVED', date__gte=month_start)
        ),
    )

    bill_stats = bill_qs.aggregate(
        count_unpaid=Count('id', filter=Q(status='UNPAID')),
        total_unpaid=Sum('total_amount', filter=Q(status='UNPAID')),
        count_overdue=Count(
            'id',
            filter=Q(status='UNPAID', due_date__lt=today, due_date__isnull=False)
        ),
    )

    recent_pos = po_qs.select_related('vendor').order_by('-date', '-created_at')[:8]
    recent_bills = bill_qs.select_related('vendor').order_by('-bill_date', '-created_at')[:5]

    context = {
        'po_stats': {
            'count_draft':          po_stats['count_draft'] or 0,
            'count_sent':           po_stats['count_sent'] or 0,
            'count_received':       po_stats['count_received'] or 0,
            'total_pending_value':  po_stats['total_pending_value'] or Decimal('0'),
            'total_received_month': po_stats['total_received_month'] or Decimal('0'),
        },
        'bill_stats': {
            'count_unpaid':  bill_stats['count_unpaid'] or 0,
            'total_unpaid':  bill_stats['total_unpaid'] or Decimal('0'),
            'count_overdue': bill_stats['count_overdue'] or 0,
        },
        'recent_pos':   recent_pos,
        'recent_bills': recent_bills,
        'today':        today,
        'rupee':        RUPEE,
    }
    return render(request, 'purchasing/purchasing_hub.html', context)
