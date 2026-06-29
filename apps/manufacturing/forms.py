from django import forms
from django.forms import inlineformset_factory
from .models import (
    BillOfMaterials, BOMItem, WorkOrder, WorkOrderMaterial,
    ProductionRun, QualityCheck, Machine, MachineLog
)
from apps.utils.nepali_date import NepaliDateWidget, NepaliDateField, FiscalYearDateMixin


class BOMForm(forms.ModelForm):
    class Meta:
        model = BillOfMaterials
        fields = ['finished_product', 'version', 'is_active', 'yield_quantity',
                  'yield_unit', 'production_time_hours', 'notes']
        widgets = {'notes': forms.Textarea(attrs={'rows': 2})}

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        if self.request and not self.request.user.is_superuser:
            from apps.products.models import Product
            self.fields['finished_product'].queryset = Product.active_objects.filter(
                company=self.request.user_company
            )


class BOMItemForm(forms.ModelForm):
    class Meta:
        model = BOMItem
        fields = ['raw_material', 'quantity', 'unit', 'scrap_percent', 'notes']
        widgets = {
            'quantity': forms.NumberInput(attrs={'step': '0.001', 'min': '0'}),
            'scrap_percent': forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'max': '100'}),
        }

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        if self.request and not self.request.user.is_superuser:
            from apps.products.models import Product
            self.fields['raw_material'].queryset = Product.active_objects.filter(
                company=self.request.user_company
            )


BOMItemFormSet = inlineformset_factory(
    BillOfMaterials, BOMItem,
    form=BOMItemForm,
    extra=1, can_delete=True,
)


class WorkOrderForm(FiscalYearDateMixin, forms.ModelForm):
    planned_start_date = NepaliDateField(widget=NepaliDateWidget(), required=False, label='Planned Start (BS)')
    planned_end_date   = NepaliDateField(widget=NepaliDateWidget(), required=False, label='Planned End (BS)')

    class Meta:
        model = WorkOrder
        fields = ['bom', 'planned_quantity', 'planned_start_date', 'planned_end_date',
                  'sales_order', 'cost_centre', 'notes']
        widgets = {
            'planned_quantity': forms.NumberInput(attrs={'step': '0.001', 'min': '0'}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        if self.request and not self.request.user.is_superuser:
            from apps.projects.models import CostCentre
            from apps.orders.models import SalesOrder
            company = self.request.user_company
            self.fields['bom'].queryset = BillOfMaterials.active_objects.filter(
                company=company, is_active=True
            )
            self.fields['sales_order'].queryset = SalesOrder.active_objects.filter(
                company=company, status__in=['CONFIRMED', 'PROCESSING']
            )
            self.fields['cost_centre'].queryset = CostCentre.active_objects.filter(company=company)
        self.inject_fiscal_year(self.request)


class ProductionRunForm(FiscalYearDateMixin, forms.ModelForm):
    run_date = NepaliDateField(widget=NepaliDateWidget(), required=True, label='Run Date (BS)')

    class Meta:
        model = ProductionRun
        fields = ['run_date', 'quantity_produced', 'quantity_rejected',
                  'operator_name', 'machine', 'shift', 'notes']
        widgets = {
            'quantity_produced': forms.NumberInput(attrs={'step': '0.001', 'min': '0'}),
            'quantity_rejected': forms.NumberInput(attrs={'step': '0.001', 'min': '0'}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        if self.request and not self.request.user.is_superuser:
            self.fields['machine'].queryset = Machine.active_objects.filter(
                company=self.request.user_company, status='OPERATIONAL'
            )
        self.inject_fiscal_year(self.request)


class QualityCheckForm(FiscalYearDateMixin, forms.ModelForm):
    check_date = NepaliDateField(widget=NepaliDateWidget(), required=True, label='Check Date (BS)')

    class Meta:
        model = QualityCheck
        fields = ['check_date', 'inspector_name', 'result', 'quantity_inspected',
                  'quantity_passed', 'quantity_failed', 'defect_description',
                  'corrective_action', 'notes']
        widgets = {
            'defect_description': forms.Textarea(attrs={'rows': 2}),
            'corrective_action': forms.Textarea(attrs={'rows': 2}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        self.inject_fiscal_year(self.request)


class MachineForm(forms.ModelForm):
    purchase_date          = NepaliDateField(widget=NepaliDateWidget(), required=False, label='Purchase Date (BS)')
    last_maintenance_date  = NepaliDateField(widget=NepaliDateWidget(), required=False, label='Last Maintenance (BS)')
    next_maintenance_date  = NepaliDateField(widget=NepaliDateWidget(), required=False, label='Next Maintenance (BS)')

    class Meta:
        model = Machine
        fields = ['name', 'machine_code', 'machine_type', 'status', 'location',
                  'purchase_date', 'last_maintenance_date', 'next_maintenance_date',
                  'hourly_cost', 'notes']
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 2}),
        }


class MachineLogForm(FiscalYearDateMixin, forms.ModelForm):
    log_date = NepaliDateField(widget=NepaliDateWidget(), required=True, label='Date (BS)')

    class Meta:
        model = MachineLog
        fields = ['log_date', 'log_type', 'hours_used', 'description', 'technician_name', 'cost']
        widgets = {'description': forms.Textarea(attrs={'rows': 2})}

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        self.inject_fiscal_year(self.request)
