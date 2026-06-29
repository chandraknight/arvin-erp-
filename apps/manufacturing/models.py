"""
apps/manufacturing/models.py
============================
Manufacturing module — Bill of Materials, Work Orders, Production Runs,
Quality Control, and Machine/Resource management.

Enabled per-company via Company.enable_manufacturing = True
(auto-enabled when Company.organisation_type = 'MANUFACTURING').

Models
------
BillOfMaterials (BOM)  — Recipe/formula for producing a finished product.
BOMItem                — A raw material or sub-assembly line in a BOM.
WorkOrder              — A production order to manufacture a quantity of a product.
WorkOrderMaterial      — Actual material consumption recorded against a work order.
ProductionRun          — A batch production event linked to a work order.
QualityCheck           — Quality inspection record for a production run.
Machine                — A machine/equipment resource used in production.
MachineLog             — Usage/maintenance log for a machine.
"""

from decimal import Decimal
from apps.utils.baseModel import BaseModel
from django.db import models
from django.utils import timezone


WORK_ORDER_STATUS = [
    ('DRAFT',       'Draft'),
    ('PLANNED',     'Planned'),
    ('IN_PROGRESS', 'In Progress'),
    ('COMPLETED',   'Completed'),
    ('CANCELLED',   'Cancelled'),
    ('ON_HOLD',     'On Hold'),
]

QC_RESULT_CHOICES = [
    ('PASS',    'Pass'),
    ('FAIL',    'Fail'),
    ('PARTIAL', 'Partial Pass'),
    ('PENDING', 'Pending'),
]

MACHINE_STATUS_CHOICES = [
    ('OPERATIONAL', 'Operational'),
    ('MAINTENANCE', 'Under Maintenance'),
    ('BREAKDOWN',   'Breakdown'),
    ('IDLE',        'Idle'),
    ('RETIRED',     'Retired'),
]


# ─────────────────────────────────────────────────────────────────────────────
# Bill of Materials
# ─────────────────────────────────────────────────────────────────────────────

class BillOfMaterials(BaseModel):
    """
    Recipe/formula for producing a finished product.
    A product can have multiple BOM versions (only one active at a time).
    """
    company = models.ForeignKey(
        'company.Company', on_delete=models.CASCADE, related_name='boms'
    )
    finished_product = models.ForeignKey(
        'products.Product', on_delete=models.CASCADE, related_name='boms',
        help_text='The product this BOM produces.'
    )
    version = models.CharField(max_length=20, default='v1',
                               help_text='BOM version (e.g. v1, v2, 2081-A).')
    is_active = models.BooleanField(default=True,
                                    help_text='Only one active BOM per product.')
    yield_quantity = models.DecimalField(
        max_digits=10, decimal_places=3, default=Decimal('1.000'),
        help_text='Quantity of finished product produced per BOM run.'
    )
    yield_unit = models.CharField(max_length=20, default='pcs',
                                  help_text='Unit of the finished product (pcs, kg, litre, etc.)')
    production_time_hours = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        help_text='Estimated production time in hours.'
    )
    notes = models.TextField(blank=True, null=True)

    class Meta:
        unique_together = ('company', 'finished_product', 'version')
        ordering = ['finished_product__name', 'version']

    def __str__(self):
        return f"BOM: {self.finished_product.name} ({self.version})"

    @property
    def total_material_cost(self):
        return sum(
            (item.quantity * (item.raw_material.cost_price or Decimal('0')))
            for item in self.items.filter(is_deleted=False)
            if item.raw_material
        )


class BOMItem(BaseModel):
    """A raw material or sub-assembly required by a BOM."""
    bom = models.ForeignKey(BillOfMaterials, on_delete=models.CASCADE, related_name='items')
    raw_material = models.ForeignKey(
        'products.Product', on_delete=models.CASCADE, related_name='used_in_boms',
        help_text='Raw material or sub-assembly.'
    )
    quantity = models.DecimalField(max_digits=10, decimal_places=3,
                                   help_text='Quantity needed per BOM yield.')
    unit = models.CharField(max_length=20, default='pcs')
    scrap_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('0.00'),
        help_text='Expected scrap/waste percentage.'
    )
    notes = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        unique_together = ('bom', 'raw_material')
        ordering = ['raw_material__name']

    def __str__(self):
        return f"{self.quantity} {self.unit} of {self.raw_material.name}"

    @property
    def quantity_with_scrap(self):
        """Quantity including scrap allowance."""
        return self.quantity * (1 + self.scrap_percent / 100)


# ─────────────────────────────────────────────────────────────────────────────
# Work Order
# ─────────────────────────────────────────────────────────────────────────────

class WorkOrder(BaseModel):
    """
    A production order to manufacture a specific quantity of a product.
    Drives material reservation and production scheduling.
    """
    company = models.ForeignKey(
        'company.Company', on_delete=models.CASCADE, related_name='work_orders'
    )
    bom = models.ForeignKey(
        BillOfMaterials, on_delete=models.PROTECT, related_name='work_orders',
        help_text='BOM to use for this production run.'
    )
    work_order_number = models.CharField(max_length=50, unique=True, blank=True, null=True)
    status = models.CharField(max_length=15, choices=WORK_ORDER_STATUS, default='DRAFT')

    # Quantities
    planned_quantity = models.DecimalField(max_digits=10, decimal_places=3)
    produced_quantity = models.DecimalField(
        max_digits=10, decimal_places=3, default=Decimal('0.000')
    )
    rejected_quantity = models.DecimalField(
        max_digits=10, decimal_places=3, default=Decimal('0.000')
    )

    # Scheduling
    planned_start_date = models.DateField(null=True, blank=True)
    planned_end_date = models.DateField(null=True, blank=True)
    actual_start_date = models.DateField(null=True, blank=True)
    actual_end_date = models.DateField(null=True, blank=True)

    # Links
    sales_order = models.ForeignKey(
        'orders.SalesOrder', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='work_orders',
        help_text='Sales order that triggered this work order (optional).'
    )
    cost_centre = models.ForeignKey(
        'projects.CostCentre', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='work_orders'
    )
    notes = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-planned_start_date', '-created_at']

    def __str__(self):
        return f"WO-{self.work_order_number or self.id}"

    @property
    def yield_percent(self):
        if self.planned_quantity and self.planned_quantity > 0:
            return round((self.produced_quantity / self.planned_quantity) * 100, 1)
        return None

    @property
    def is_complete(self):
        return self.status == 'COMPLETED'

    @property
    def total_material_cost(self):
        return self.material_consumption.filter(is_deleted=False).aggregate(
            t=models.Sum(models.F('quantity_used') * models.F('unit_cost'))
        )['t'] or Decimal('0.00')


class WorkOrderMaterial(BaseModel):
    """Actual material consumption recorded against a work order."""
    work_order = models.ForeignKey(
        WorkOrder, on_delete=models.CASCADE, related_name='material_consumption'
    )
    bom_item = models.ForeignKey(
        BOMItem, on_delete=models.SET_NULL, null=True, blank=True,
        help_text='BOM item this consumption is for.'
    )
    raw_material = models.ForeignKey(
        'products.Product', on_delete=models.CASCADE, related_name='consumed_in_production'
    )
    quantity_planned = models.DecimalField(max_digits=10, decimal_places=3)
    quantity_used = models.DecimalField(max_digits=10, decimal_places=3, default=Decimal('0.000'))
    unit_cost = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0.00'),
        help_text='Cost per unit at time of consumption.'
    )
    notes = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return f"{self.quantity_used} of {self.raw_material.name} for {self.work_order}"

    @property
    def total_cost(self):
        return self.quantity_used * self.unit_cost

    @property
    def variance(self):
        return self.quantity_used - self.quantity_planned


# ─────────────────────────────────────────────────────────────────────────────
# Production Run
# ─────────────────────────────────────────────────────────────────────────────

class ProductionRun(BaseModel):
    """
    A batch production event — records actual output for a work order.
    A work order can have multiple production runs (partial batches).
    """
    work_order = models.ForeignKey(
        WorkOrder, on_delete=models.CASCADE, related_name='production_runs'
    )
    run_number = models.CharField(max_length=50, blank=True, null=True)
    run_date = models.DateField(default=timezone.now)
    quantity_produced = models.DecimalField(max_digits=10, decimal_places=3)
    quantity_rejected = models.DecimalField(
        max_digits=10, decimal_places=3, default=Decimal('0.000')
    )
    operator_name = models.CharField(max_length=255, blank=True, null=True)
    machine = models.ForeignKey(
        'manufacturing.Machine', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='production_runs'
    )
    shift = models.CharField(
        max_length=10,
        choices=[('MORNING', 'Morning'), ('AFTERNOON', 'Afternoon'), ('NIGHT', 'Night')],
        blank=True, null=True
    )
    notes = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-run_date', '-created_at']

    def __str__(self):
        return f"Run {self.run_number or self.id} — {self.work_order}"

    @property
    def yield_percent(self):
        total = self.quantity_produced + self.quantity_rejected
        if total > 0:
            return round((self.quantity_produced / total) * 100, 1)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Quality Control
# ─────────────────────────────────────────────────────────────────────────────

class QualityCheck(BaseModel):
    """Quality inspection record for a production run."""
    production_run = models.ForeignKey(
        ProductionRun, on_delete=models.CASCADE, related_name='quality_checks'
    )
    check_date = models.DateField(default=timezone.now)
    inspector_name = models.CharField(max_length=255)
    result = models.CharField(max_length=10, choices=QC_RESULT_CHOICES, default='PENDING')
    quantity_inspected = models.DecimalField(max_digits=10, decimal_places=3)
    quantity_passed = models.DecimalField(max_digits=10, decimal_places=3, default=Decimal('0.000'))
    quantity_failed = models.DecimalField(max_digits=10, decimal_places=3, default=Decimal('0.000'))
    defect_description = models.TextField(blank=True, null=True)
    corrective_action = models.TextField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-check_date']

    def __str__(self):
        return f"QC {self.result} — {self.production_run} ({self.check_date})"


# ─────────────────────────────────────────────────────────────────────────────
# Machine / Resource
# ─────────────────────────────────────────────────────────────────────────────

class Machine(BaseModel):
    """A machine or equipment resource used in production."""
    company = models.ForeignKey(
        'company.Company', on_delete=models.CASCADE, related_name='machines'
    )
    name = models.CharField(max_length=255)
    machine_code = models.CharField(max_length=50, blank=True, null=True)
    machine_type = models.CharField(max_length=100, blank=True, null=True,
                                    help_text='e.g. CNC, Lathe, Mixer, Conveyor')
    status = models.CharField(max_length=15, choices=MACHINE_STATUS_CHOICES, default='OPERATIONAL')
    location = models.CharField(max_length=255, blank=True, null=True)
    purchase_date = models.DateField(null=True, blank=True)
    last_maintenance_date = models.DateField(null=True, blank=True)
    next_maintenance_date = models.DateField(null=True, blank=True)
    hourly_cost = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal('0.00'),
        help_text='Operating cost per hour.'
    )
    notes = models.TextField(blank=True, null=True)

    class Meta:
        unique_together = ('company', 'machine_code')
        ordering = ['name']

    def __str__(self):
        return f"{self.machine_code} — {self.name}" if self.machine_code else self.name


class MachineLog(BaseModel):
    """Usage or maintenance log entry for a machine."""
    machine = models.ForeignKey(Machine, on_delete=models.CASCADE, related_name='logs')
    log_date = models.DateField(default=timezone.now)
    log_type = models.CharField(
        max_length=15,
        choices=[
            ('USAGE',       'Usage'),
            ('MAINTENANCE', 'Maintenance'),
            ('BREAKDOWN',   'Breakdown'),
            ('REPAIR',      'Repair'),
            ('INSPECTION',  'Inspection'),
        ],
        default='USAGE'
    )
    hours_used = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('0.00'))
    description = models.TextField(blank=True, null=True)
    technician_name = models.CharField(max_length=255, blank=True, null=True)
    cost = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'),
                               help_text='Cost of maintenance/repair if applicable.')

    class Meta:
        ordering = ['-log_date']

    def __str__(self):
        return f"{self.machine.name} — {self.log_type} on {self.log_date}"
