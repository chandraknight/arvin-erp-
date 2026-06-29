from decimal import Decimal

from django import forms
from django.forms import inlineformset_factory
from .models import SalesOrder, SalesOrderItem, DeliveryNote, DeliveryNoteItem, DeliveryTracking
from apps.utils.nepali_date import NepaliDateWidget, NepaliDateField, FiscalYearDateMixin


class SalesOrderForm(FiscalYearDateMixin, forms.ModelForm):
    order_date = NepaliDateField(widget=NepaliDateWidget(), required=True, label='Order Date (BS)')
    expected_delivery_date = NepaliDateField(widget=NepaliDateWidget(), required=False, label='Expected Delivery (BS)')

    class Meta:
        model = SalesOrder
        fields = [
            'customer', 'branch', 'order_date', 'expected_delivery_date',
            'priority', 'delivery_address', 'delivery_contact', 'delivery_phone',
            'delivery_charge', 'notes',
        ]
        widgets = {
            'delivery_address': forms.Textarea(attrs={'rows': 2}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        if self.request and not self.request.user.is_superuser:
            from apps.customers.models import Customer
            from apps.company.models import Branch
            company = self.request.user_company
            self.fields['customer'].queryset = Customer.active_objects.filter(company=company)
            self.fields['branch'].queryset = Branch.active_objects.filter(company=company)
            if not company.enable_branch_accounting:
                del self.fields['branch']
        self.inject_fiscal_year(self.request)


class SalesOrderItemForm(forms.ModelForm):
    class Meta:
        model = SalesOrderItem
        fields = ['product', 'description', 'quantity', 'unit_price', 'discount_percent', 'tax_percent']
        widgets = {
            'quantity': forms.NumberInput(attrs={'step': '0.001', 'min': '0'}),
            'unit_price': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'discount_percent': forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'max': '100'}),
            'tax_percent': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
        }

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        if self.request and not self.request.user.is_superuser:
            from apps.products.models import Product
            self.fields['product'].queryset = Product.active_objects.filter(
                company=self.request.user_company
            )
        self.fields['product'].required = False
        # Allow empty rows added by JS to pass formset validation; view skips rows with no product
        self.fields['unit_price'].required = False
        self.fields['quantity'].initial = Decimal('1.000')


SalesOrderItemFormSet = inlineformset_factory(
    SalesOrder, SalesOrderItem,
    form=SalesOrderItemForm,
    extra=0, can_delete=True, max_num=100,
)


class DeliveryNoteForm(FiscalYearDateMixin, forms.ModelForm):
    dispatch_date = NepaliDateField(widget=NepaliDateWidget(), required=True, label='Dispatch Date (BS)')
    expected_delivery_date = NepaliDateField(widget=NepaliDateWidget(), required=False, label='Expected Delivery (BS)')

    class Meta:
        model = DeliveryNote
        fields = [
            'dispatch_date', 'expected_delivery_date',
            'carrier_name', 'tracking_number', 'vehicle_number',
            'driver_name', 'driver_phone',
            'delivery_address', 'delivery_contact', 'delivery_phone',
            'notes',
        ]
        widgets = {
            'delivery_address': forms.Textarea(attrs={'rows': 2}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        self.inject_fiscal_year(self.request)


class DeliveryTrackingForm(forms.ModelForm):
    class Meta:
        model = DeliveryTracking
        fields = ['status', 'location', 'latitude', 'longitude', 'notes', 'updated_by_name']
        widgets = {'notes': forms.TextInput()}
