from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.db.models import Q, Sum, F, ExpressionWrapper, DecimalField
from django.db import transaction
from decimal import Decimal

from apps.utils.mixins import AuthMixin
from apps.utils.htmx import is_htmx
from .models import (
    BillOfMaterials, BOMItem, WorkOrder, WorkOrderMaterial,
    ProductionRun, QualityCheck, Machine, MachineLog
)
from .forms import (
    BOMForm, BOMItemFormSet, WorkOrderForm, ProductionRunForm,
    QualityCheckForm, MachineForm, MachineLogForm
)


def _require_manufacturing(request):
    company = request.user_company
    if company and not company.enable_manufacturing:
        messages.warning(request, "Manufacturing module is not enabled for your company.")
        return redirect('accounts:user_dashboard')
    return None


# ── Dashboard ─────────────────────────────────────────────────────────────────

@login_required
def manufacturing_dashboard(request):
    guard = _require_manufacturing(request)
    if guard:
        return guard

    company = request.user_company
    work_orders = WorkOrder.active_objects.filter(company=company)

    stats = {
        'total_boms': BillOfMaterials.active_objects.filter(company=company, is_active=True).count(),
        'open_work_orders': work_orders.filter(status__in=['PLANNED', 'IN_PROGRESS']).count(),
        'completed_this_month': work_orders.filter(status='COMPLETED').count(),
        'machines_operational': Machine.active_objects.filter(company=company, status='OPERATIONAL').count(),
        'machines_maintenance': Machine.active_objects.filter(company=company, status='MAINTENANCE').count(),
    }

    recent_work_orders = work_orders.select_related(
        'bom__finished_product'
    ).order_by('-created_at')[:10]

    from django.utils import timezone
    today = timezone.now().date()

    machines_needing_maintenance = Machine.active_objects.filter(
        company=company,
        status__in=['MAINTENANCE', 'BREAKDOWN']
    )
    # Machines with overdue or due-within-7-days maintenance
    from datetime import timedelta
    maintenance_due_soon = Machine.active_objects.filter(
        company=company,
        status='OPERATIONAL',
        next_maintenance_date__lte=today + timedelta(days=7),
    ).exclude(next_maintenance_date__isnull=True)

    return render(request, 'manufacturing/dashboard.html', {
        'stats': stats,
        'recent_work_orders': recent_work_orders,
        'machines_needing_maintenance': machines_needing_maintenance,
        'maintenance_due_soon': maintenance_due_soon,
        'today': today,
    })


# ── Bill of Materials ─────────────────────────────────────────────────────────

class BOMListView(AuthMixin, ListView):
    model = BillOfMaterials
    template_name = 'manufacturing/bom_list.html'
    context_object_name = 'boms'
    permission_required = ['manufacturing.view_billofmaterials']
    paginate_by = 20

    def get_queryset(self):
        qs = BillOfMaterials.active_objects.filter(
            company=self.request.user_company
        ).select_related('finished_product')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(finished_product__name__icontains=q)
        return qs.order_by('finished_product__name', 'version')

    def get_template_names(self):
        if is_htmx(self.request):
            return ['manufacturing/partials/bom_table.html']
        return [self.template_name]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['q'] = self.request.GET.get('q', '')
        return ctx


class BOMDetailView(AuthMixin, DetailView):
    model = BillOfMaterials
    template_name = 'manufacturing/bom_detail.html'
    context_object_name = 'bom'
    permission_required = ['manufacturing.view_billofmaterials']

    def get_queryset(self):
        return BillOfMaterials.active_objects.filter(company=self.request.user_company)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['items'] = self.object.items.filter(is_deleted=False).select_related('raw_material')
        return ctx


class BOMCreateView(AuthMixin, CreateView):
    model = BillOfMaterials
    form_class = BOMForm
    template_name = 'manufacturing/bom_form.html'
    permission_required = ['manufacturing.add_billofmaterials']

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw['request'] = self.request
        return kw

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if self.request.POST:
            ctx['item_formset'] = BOMItemFormSet(self.request.POST)
        else:
            ctx['item_formset'] = BOMItemFormSet()
        return ctx

    def form_valid(self, form):
        ctx = self.get_context_data()
        item_formset = ctx['item_formset']
        if item_formset.is_valid():
            form.instance.company = self.request.user_company
            form.instance.created_by = self.request.user
            self.object = form.save()
            item_formset.instance = self.object
            item_formset.save()
            messages.success(self.request, f"BOM for {self.object.finished_product.name} created.")
            return redirect('manufacturing:bom_detail', pk=self.object.pk)
        return self.form_invalid(form)


class BOMUpdateView(AuthMixin, UpdateView):
    model = BillOfMaterials
    form_class = BOMForm
    template_name = 'manufacturing/bom_form.html'
    permission_required = ['manufacturing.change_billofmaterials']

    def get_queryset(self):
        return BillOfMaterials.active_objects.filter(company=self.request.user_company)

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw['request'] = self.request
        return kw

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if self.request.POST:
            ctx['item_formset'] = BOMItemFormSet(self.request.POST, instance=self.object)
        else:
            ctx['item_formset'] = BOMItemFormSet(instance=self.object)
        return ctx

    def form_valid(self, form):
        ctx = self.get_context_data()
        item_formset = ctx['item_formset']
        if item_formset.is_valid():
            form.instance.updated_by = self.request.user
            self.object = form.save()
            item_formset.save()
            messages.success(self.request, "BOM updated.")
            return redirect('manufacturing:bom_detail', pk=self.object.pk)
        return self.form_invalid(form)


class BOMDeleteView(AuthMixin, DeleteView):
    model = BillOfMaterials
    template_name = 'manufacturing/confirm_delete.html'
    success_url = reverse_lazy('manufacturing:bom_list')
    permission_required = ['manufacturing.delete_billofmaterials']

    def get_queryset(self):
        return BillOfMaterials.active_objects.filter(company=self.request.user_company)

    def form_valid(self, form):
        self.object.soft_delete(deleted_by=self.request.user)
        messages.success(self.request, "BOM deleted.")
        return redirect(self.success_url)


# ── Work Orders ───────────────────────────────────────────────────────────────

class WorkOrderListView(AuthMixin, ListView):
    model = WorkOrder
    template_name = 'manufacturing/workorder_list.html'
    context_object_name = 'work_orders'
    permission_required = ['manufacturing.view_workorder']
    paginate_by = 20

    def get_queryset(self):
        qs = WorkOrder.active_objects.filter(
            company=self.request.user_company
        ).select_related('bom__finished_product')
        status = self.request.GET.get('status', '').strip()
        if status:
            qs = qs.filter(status=status)
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(work_order_number__icontains=q) |
                Q(bom__finished_product__name__icontains=q)
            )
        return qs.order_by('-planned_start_date')

    def get_template_names(self):
        if is_htmx(self.request):
            return ['manufacturing/partials/workorder_table.html']
        return [self.template_name]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['q'] = self.request.GET.get('q', '')
        ctx['status'] = self.request.GET.get('status', '')
        return ctx


class WorkOrderDetailView(AuthMixin, DetailView):
    model = WorkOrder
    template_name = 'manufacturing/workorder_detail.html'
    context_object_name = 'work_order'
    permission_required = ['manufacturing.view_workorder']

    def get_queryset(self):
        return WorkOrder.active_objects.filter(company=self.request.user_company)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['production_runs'] = self.object.production_runs.filter(
            is_deleted=False
        ).order_by('-run_date')
        ctx['materials'] = self.object.material_consumption.filter(
            is_deleted=False
        ).select_related('raw_material')
        ctx['run_form'] = ProductionRunForm(request=self.request)
        return ctx


class WorkOrderCreateView(AuthMixin, CreateView):
    model = WorkOrder
    form_class = WorkOrderForm
    template_name = 'manufacturing/workorder_form.html'
    permission_required = ['manufacturing.add_workorder']

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw['request'] = self.request
        return kw

    def form_valid(self, form):
        from django.utils import timezone
        company = self.request.user_company

        with transaction.atomic():
            # Lock company's latest WO to prevent concurrent duplicate numbers.
            # Use count-of-existing (scoped to company+year) so numbers never
            # collide across companies even though field is globally unique.
            year = timezone.now().year
            last = (
                WorkOrder.objects.select_for_update()
                .filter(company=company, work_order_number__startswith=f"WO-{year}-")
                .order_by('-work_order_number')
                .first()
            )
            if last and last.work_order_number:
                try:
                    seq = int(last.work_order_number.rsplit('-', 1)[-1]) + 1
                except (ValueError, IndexError):
                    seq = WorkOrder.objects.filter(company=company).count() + 1
            else:
                seq = 1
            form.instance.company = company
            form.instance.created_by = self.request.user
            form.instance.work_order_number = f"WO-{year}-{company.pk.hex[:6].upper()}-{seq:04d}"
            self.object = form.save()

            bom = self.object.bom
            for bom_item in bom.items.filter(is_deleted=False):
                planned_qty = (
                    bom_item.quantity_with_scrap * self.object.planned_quantity / bom.yield_quantity
                )
                WorkOrderMaterial.objects.create(
                    work_order=self.object,
                    bom_item=bom_item,
                    raw_material=bom_item.raw_material,
                    quantity_planned=planned_qty,
                    unit_cost=getattr(bom_item.raw_material, 'cost_price', Decimal('0')) or Decimal('0'),
                    created_by=self.request.user,
                )

        messages.success(self.request, f"Work order {self.object.work_order_number} created.")
        return redirect('manufacturing:workorder_detail', pk=self.object.pk)


class WorkOrderUpdateView(AuthMixin, UpdateView):
    model = WorkOrder
    form_class = WorkOrderForm
    template_name = 'manufacturing/workorder_form.html'
    permission_required = ['manufacturing.change_workorder']

    def get_queryset(self):
        return WorkOrder.active_objects.filter(
            company=self.request.user_company,
            status__in=['DRAFT', 'PLANNED']
        )

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw['request'] = self.request
        return kw

    def get_success_url(self):
        return reverse_lazy('manufacturing:workorder_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        messages.success(self.request, "Work order updated.")
        return super().form_valid(form)


@login_required
def start_work_order(request, pk):
    wo = get_object_or_404(WorkOrder, pk=pk, company=request.user_company, status='PLANNED')

    # Check material availability before starting
    from apps.products.models import ProductStock
    shortfalls = []
    for mat in wo.material_consumption.filter(is_deleted=False):
        stock = ProductStock.objects.filter(product=mat.raw_material).first()
        available = stock.stock if stock else Decimal('0')
        if available < mat.quantity_planned:
            shortfalls.append(
                f"{mat.raw_material.name}: need {mat.quantity_planned}, have {available}"
            )
    if shortfalls:
        messages.error(
            request,
            "Cannot start — insufficient stock: " + "; ".join(shortfalls),
        )
        return redirect('manufacturing:workorder_detail', pk=pk)

    from django.utils import timezone
    wo.status = 'IN_PROGRESS'
    wo.actual_start_date = timezone.now().date()
    wo.updated_by = request.user
    wo.save(update_fields=['status', 'actual_start_date', 'updated_by'])
    messages.success(request, f"Work order {wo.work_order_number} started.")
    return redirect('manufacturing:workorder_detail', pk=pk)


@login_required
def complete_work_order(request, pk):
    wo = get_object_or_404(WorkOrder, pk=pk, company=request.user_company, status='IN_PROGRESS')
    from django.utils import timezone
    from apps.products.models import ProductStock

    total_produced = wo.production_runs.filter(is_deleted=False).aggregate(
        t=Sum('quantity_produced')
    )['t'] or Decimal('0')
    total_rejected = wo.production_runs.filter(is_deleted=False).aggregate(
        t=Sum('quantity_rejected')
    )['t'] or Decimal('0')

    with transaction.atomic():
        wo.status = 'COMPLETED'
        wo.actual_end_date = timezone.now().date()
        wo.produced_quantity = total_produced
        wo.rejected_quantity = total_rejected
        wo.updated_by = request.user
        wo.save(update_fields=['status', 'actual_end_date', 'produced_quantity', 'rejected_quantity', 'updated_by'])

        # Deduct actual material usage from inventory (select_for_update to prevent race)
        for mat in wo.material_consumption.filter(is_deleted=False):
            used = mat.quantity_used or mat.quantity_planned
            ProductStock.objects.get_or_create(product=mat.raw_material)
            ProductStock.objects.select_for_update().filter(
                product=mat.raw_material
            ).update(stock=F('stock') - used)
            # Clamp to zero — F() can go negative on concurrent deductions
            ProductStock.objects.filter(product=mat.raw_material, stock__lt=0).update(stock=0)

        # Add finished goods to inventory
        if total_produced > 0:
            ProductStock.objects.get_or_create(product=wo.bom.finished_product)
            ProductStock.objects.select_for_update().filter(
                product=wo.bom.finished_product
            ).update(stock=F('stock') + total_produced)

    messages.success(request, f"Work order {wo.work_order_number} completed. Produced: {total_produced}.")
    return redirect('manufacturing:workorder_detail', pk=pk)


# ── Production Runs ───────────────────────────────────────────────────────────

class ProductionRunCreateView(AuthMixin, CreateView):
    model = ProductionRun
    form_class = ProductionRunForm
    template_name = 'manufacturing/run_form.html'
    permission_required = ['manufacturing.add_productionrun']

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw['request'] = self.request
        return kw

    def form_valid(self, form):
        wo = get_object_or_404(
            WorkOrder, pk=self.kwargs['wo_pk'], company=self.request.user_company
        )
        with transaction.atomic():
            wo = WorkOrder.objects.select_for_update().get(pk=wo.pk)
            count = wo.production_runs.count() + 1
            form.instance.work_order = wo
            form.instance.created_by = self.request.user
            form.instance.run_number = f"{wo.work_order_number}-R{count:02d}"
            self.object = form.save()

            total = wo.production_runs.filter(is_deleted=False).aggregate(
                t=Sum('quantity_produced')
            )['t'] or Decimal('0')
            wo.produced_quantity = total
            if wo.status == 'PLANNED':
                wo.status = 'IN_PROGRESS'
                wo.actual_start_date = form.cleaned_data.get('run_date')
            wo.save(update_fields=['produced_quantity', 'status', 'actual_start_date'])

        messages.success(self.request, f"Production run {self.object.run_number} recorded.")
        return redirect('manufacturing:workorder_detail', pk=wo.pk)


class ProductionRunDetailView(AuthMixin, DetailView):
    model = ProductionRun
    template_name = 'manufacturing/run_detail.html'
    context_object_name = 'run'
    permission_required = ['manufacturing.view_productionrun']

    def get_queryset(self):
        return ProductionRun.active_objects.filter(
            work_order__company=self.request.user_company
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['qc_checks'] = self.object.quality_checks.filter(is_deleted=False)
        ctx['qc_form'] = QualityCheckForm(request=self.request)
        return ctx


# ── Quality Control ───────────────────────────────────────────────────────────

class QualityCheckCreateView(AuthMixin, CreateView):
    model = QualityCheck
    form_class = QualityCheckForm
    template_name = 'manufacturing/qc_form.html'
    permission_required = ['manufacturing.add_qualitycheck']

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw['request'] = self.request
        return kw

    def form_valid(self, form):
        run = get_object_or_404(
            ProductionRun, pk=self.kwargs['run_pk'],
            work_order__company=self.request.user_company
        )
        form.instance.production_run = run
        form.instance.created_by = self.request.user
        self.object = form.save()

        # When QC finds failures, increment run's rejected quantity
        if form.cleaned_data.get('result') in ('FAIL', 'PARTIAL') and form.cleaned_data.get('quantity_failed'):
            run.quantity_rejected = (run.quantity_rejected or Decimal('0')) + form.cleaned_data['quantity_failed']
            run.save(update_fields=['quantity_rejected'])

        messages.success(self.request, "Quality check recorded.")
        return redirect('manufacturing:run_detail', pk=run.pk)


# ── Machines ──────────────────────────────────────────────────────────────────

class MachineListView(AuthMixin, ListView):
    model = Machine
    template_name = 'manufacturing/machine_list.html'
    context_object_name = 'machines'
    permission_required = ['manufacturing.view_machine']

    def get_queryset(self):
        return Machine.active_objects.filter(
            company=self.request.user_company
        ).order_by('name')


class MachineDetailView(AuthMixin, DetailView):
    model = Machine
    template_name = 'manufacturing/machine_detail.html'
    context_object_name = 'machine'
    permission_required = ['manufacturing.view_machine']

    def get_queryset(self):
        return Machine.active_objects.filter(company=self.request.user_company)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['logs'] = self.object.logs.filter(is_deleted=False).order_by('-log_date')[:20]
        ctx['log_form'] = MachineLogForm(request=self.request)
        return ctx


class MachineCreateView(AuthMixin, CreateView):
    model = Machine
    form_class = MachineForm
    template_name = 'manufacturing/machine_form.html'
    permission_required = ['manufacturing.add_machine']

    def form_valid(self, form):
        form.instance.company = self.request.user_company
        form.instance.created_by = self.request.user
        messages.success(self.request, f"Machine '{form.instance.name}' added.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('manufacturing:machine_detail', kwargs={'pk': self.object.pk})


class MachineUpdateView(AuthMixin, UpdateView):
    model = Machine
    form_class = MachineForm
    template_name = 'manufacturing/machine_form.html'
    permission_required = ['manufacturing.change_machine']

    def get_queryset(self):
        return Machine.active_objects.filter(company=self.request.user_company)

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        messages.success(self.request, "Machine updated.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('manufacturing:machine_detail', kwargs={'pk': self.object.pk})


class MachineLogCreateView(AuthMixin, CreateView):
    model = MachineLog
    form_class = MachineLogForm
    template_name = 'manufacturing/machine_log_form.html'
    permission_required = ['manufacturing.add_machinelog']

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw['request'] = self.request
        return kw

    def form_valid(self, form):
        machine = get_object_or_404(
            Machine, pk=self.kwargs['pk'], company=self.request.user_company
        )
        form.instance.machine = machine
        form.instance.created_by = self.request.user
        # Update machine status if maintenance/breakdown
        if form.cleaned_data['log_type'] in ('MAINTENANCE', 'BREAKDOWN'):
            machine.status = form.cleaned_data['log_type']
            machine.last_maintenance_date = form.cleaned_data['log_date']
            machine.save(update_fields=['status', 'last_maintenance_date'])
        elif form.cleaned_data['log_type'] == 'REPAIR':
            machine.status = 'OPERATIONAL'
            machine.save(update_fields=['status'])
        messages.success(self.request, "Machine log entry added.")
        self.object = form.save()
        return redirect('manufacturing:machine_detail', pk=machine.pk)


# ── Reports ───────────────────────────────────────────────────────────────────

@login_required
def production_report(request):
    guard = _require_manufacturing(request)
    if guard:
        return guard

    company = request.user_company
    fiscal_year_id = request.session.get('active_fiscal_year_id')
    fiscal_year = None
    if fiscal_year_id:
        from apps.company.models import FiscalYear
        fiscal_year = FiscalYear.objects.filter(id=fiscal_year_id, company=company).first()

    work_orders = WorkOrder.active_objects.filter(company=company)
    if fiscal_year:
        work_orders = work_orders.filter(
            planned_start_date__gte=fiscal_year.start_date,
            planned_start_date__lte=fiscal_year.end_date,
        )

    stats = work_orders.aggregate(
        total=Sum('planned_quantity'),
        produced=Sum('produced_quantity'),
        rejected=Sum('rejected_quantity'),
    )

    by_product = work_orders.values(
        'bom__finished_product__name'
    ).annotate(
        total_planned=Sum('planned_quantity'),
        total_produced=Sum('produced_quantity'),
        total_rejected=Sum('rejected_quantity'),
    ).order_by('bom__finished_product__name')

    return render(request, 'manufacturing/production_report.html', {
        'company': company,
        'fiscal_year': fiscal_year,
        'work_orders': work_orders.select_related('bom__finished_product').order_by('-planned_start_date'),
        'stats': stats,
        'by_product': by_product,
    })


@login_required
def material_consumption_report(request):
    guard = _require_manufacturing(request)
    if guard:
        return guard

    company = request.user_company
    consumption = WorkOrderMaterial.active_objects.filter(
        work_order__company=company
    ).values(
        'raw_material__name'
    ).annotate(
        total_planned=Sum('quantity_planned'),
        total_used=Sum('quantity_used'),
        total_cost=Sum(
            ExpressionWrapper(
                F('quantity_used') * F('unit_cost'),
                output_field=DecimalField()
            )
        ),
    ).order_by('raw_material__name')

    return render(request, 'manufacturing/material_report.html', {
        'company': company,
        'consumption': consumption,
    })


# ── Cancel Work Order ─────────────────────────────────────────────────────────

@login_required
def cancel_work_order(request, pk):
    wo = get_object_or_404(
        WorkOrder, pk=pk, company=request.user_company
    )
    if wo.status in ('COMPLETED', 'CANCELLED'):
        messages.error(request, f"Work order is already {wo.status}.")
        return redirect('manufacturing:workorder_detail', pk=pk)

    if request.method == 'POST':
        reason = request.POST.get('reason', '').strip() or 'No reason given'
        with transaction.atomic():
            wo.status = 'CANCELLED'
            wo.notes = (wo.notes or '') + f'\nCANCELLED: {reason}'
            wo.updated_by = request.user
            wo.save(update_fields=['status', 'notes', 'updated_by'])
        messages.success(request, f"Work order {wo.work_order_number} cancelled.")
        return redirect('manufacturing:workorder_list')

    return render(request, 'manufacturing/confirm_cancel.html', {'wo': wo})


# ── Material Consumption Update ───────────────────────────────────────────────

@login_required
def update_material_consumption(request, pk):
    """
    Record actual quantities used for each raw material in a work order.
    Only available while WO is IN_PROGRESS.
    """
    guard = _require_manufacturing(request)
    if guard:
        return guard

    wo = get_object_or_404(WorkOrder, pk=pk, company=request.user_company)
    if wo.status not in ('IN_PROGRESS', 'COMPLETED'):
        messages.error(request, "Material consumption can only be updated for in-progress or completed work orders.")
        return redirect('manufacturing:workorder_detail', pk=pk)

    materials = wo.material_consumption.filter(is_deleted=False).select_related('raw_material')

    if request.method == 'POST':
        errors = []
        with transaction.atomic():
            for mat in materials:
                key = f'qty_used_{mat.pk}'
                raw = request.POST.get(key, '').strip()
                if not raw:
                    continue
                try:
                    qty = Decimal(raw)
                    if qty < 0:
                        errors.append(f"{mat.raw_material.name}: quantity cannot be negative.")
                        continue
                    mat.quantity_used = qty
                    mat.unit_cost = getattr(mat.raw_material, 'cost_price', Decimal('0')) or Decimal('0')
                    mat.updated_by = request.user
                    mat.save(update_fields=['quantity_used', 'unit_cost', 'updated_by'])
                except Exception:
                    errors.append(f"{mat.raw_material.name}: invalid value '{raw}'.")

        if errors:
            for e in errors:
                messages.error(request, e)
        else:
            messages.success(request, "Material consumption updated.")
        return redirect('manufacturing:workorder_detail', pk=pk)

    return render(request, 'manufacturing/material_consumption_form.html', {
        'wo': wo,
        'materials': materials,
    })
