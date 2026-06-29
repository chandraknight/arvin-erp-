from django import forms
from .models import (
    TableSection, RestaurantTable, PrinterStation,
    DiningOrder, DiningOrderItem,
    Menu, MenuCategory, MenuItem,
    RoomType, Room, RoomBooking, RoomCharge,
)
from apps.utils.nepali_date import NepaliDateWidget, NepaliDateField


class TableSectionForm(forms.ModelForm):
    class Meta:
        model = TableSection
        fields = ['name', 'description', 'sort_order']
        widgets = {'description': forms.TextInput()}


class RestaurantTableForm(forms.ModelForm):
    class Meta:
        model = RestaurantTable
        fields = ['section', 'table_number', 'display_name', 'capacity', 'is_active']

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        if self.request and not self.request.user.is_superuser:
            company = self.request.user_company
            self.fields['section'].queryset = TableSection.active_objects.filter(company=company)
            self.fields['section'].required = False


class PrinterStationForm(forms.ModelForm):
    class Meta:
        model = PrinterStation
        fields = ['name', 'printer_type', 'ip_address', 'port', 'is_active', 'is_default', 'notes']
        widgets = {'notes': forms.TextInput()}
        help_texts = {
            'ip_address': 'IP address or hostname of the network printer (e.g. 192.168.1.100).',
            'port': 'TCP port — default 9100 for most ESC/POS thermal printers.',
        }


class DiningOrderForm(forms.ModelForm):
    class Meta:
        model = DiningOrder
        fields = ['table', 'covers', 'waiter_name', 'customer', 'notes']
        widgets = {'notes': forms.Textarea(attrs={'rows': 2})}

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        if self.request and not self.request.user.is_superuser:
            from apps.customers.models import Customer
            company = self.request.user_company
            self.fields['table'].queryset = RestaurantTable.active_objects.filter(
                company=company, is_active=True
            )
            self.fields['customer'].queryset = Customer.active_objects.filter(company=company)
            self.fields['customer'].required = False


class DiningOrderItemForm(forms.ModelForm):
    class Meta:
        model = DiningOrderItem
        fields = ['product', 'item_type', 'quantity', 'unit_price',
                  'discount_percent', 'tax_percent', 'notes']
        widgets = {
            'quantity': forms.NumberInput(attrs={'step': '1', 'min': '1', 'class': 'qty-input'}),
            'unit_price': forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'readonly': 'readonly'}),
            'discount_percent': forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'max': '100'}),
            'tax_percent': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'notes': forms.TextInput(attrs={'placeholder': 'Special instructions…'}),
        }

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        if self.request and not self.request.user.is_superuser:
            from apps.products.models import Product
            self.fields['product'].queryset = Product.active_objects.filter(
                company=self.request.user_company
            )


class TableTransferForm(forms.Form):
    """Move an open dining order from one table to another."""
    target_table = forms.ModelChoiceField(
        queryset=RestaurantTable.objects.none(),
        label='Transfer to Table',
        help_text='Only available (empty) tables are shown.',
    )

    def __init__(self, *args, **kwargs):
        company = kwargs.pop('company', None)
        current_table = kwargs.pop('current_table', None)
        super().__init__(*args, **kwargs)
        if company:
            qs = RestaurantTable.active_objects.filter(
                company=company, is_active=True, status='AVAILABLE'
            )
            if current_table:
                qs = qs.exclude(pk=current_table.pk)
            self.fields['target_table'].queryset = qs


class MenuForm(forms.ModelForm):
    valid_from = NepaliDateField(widget=NepaliDateWidget(), required=False, label='Valid From (BS)')
    valid_to   = NepaliDateField(widget=NepaliDateWidget(), required=False, label='Valid To (BS)')

    class Meta:
        model = Menu
        fields = ['name', 'description', 'valid_from', 'valid_to']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }


class MenuCategoryForm(forms.ModelForm):
    class Meta:
        model = MenuCategory
        fields = ['name', 'item_type', 'sort_order', 'is_active']
        widgets = {'sort_order': forms.NumberInput(attrs={'min': '0'})}


class MenuItemForm(forms.ModelForm):
    class Meta:
        model = MenuItem
        fields = ['product', 'price_override', 'is_available', 'sort_order', 'notes']
        widgets = {
            'price_override': forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'placeholder': 'Leave blank for product price'}),
            'sort_order': forms.NumberInput(attrs={'min': '0'}),
            'notes': forms.TextInput(attrs={'placeholder': 'e.g. Contains nuts, Vegan'}),
        }

    def __init__(self, *args, **kwargs):
        company = kwargs.pop('company', None)
        super().__init__(*args, **kwargs)
        if company:
            from apps.products.models import Product
            self.fields['product'].queryset = Product.active_objects.filter(
                company=company
            ).order_by('name')
        self.fields['price_override'].required = False


class RoomTypeForm(forms.ModelForm):
    class Meta:
        model = RoomType
        fields = ['name', 'capacity', 'rate_per_night', 'description']
        widgets = {
            'rate_per_night': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'description': forms.Textarea(attrs={'rows': 3}),
        }


class RoomForm(forms.ModelForm):
    class Meta:
        model = Room
        fields = ['room_type', 'room_number', 'floor', 'status', 'notes']

    def __init__(self, *args, **kwargs):
        company = kwargs.pop('company', None)
        super().__init__(*args, **kwargs)
        if company:
            self.fields['room_type'].queryset = RoomType.objects.filter(company=company)


class RoomBookingForm(forms.ModelForm):
    class Meta:
        model = RoomBooking
        fields = [
            'room', 'guest_name', 'guest_phone', 'guest_email',
            'check_in', 'check_out', 'adult_count', 'child_count', 'notes',
        ]
        widgets = {
            'check_in':  forms.DateInput(attrs={'type': 'date'}),
            'check_out': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        company = kwargs.pop('company', None)
        super().__init__(*args, **kwargs)
        if company:
            self.fields['room'].queryset = Room.objects.filter(
                company=company, status__in=['AVAILABLE', 'RESERVED']
            ).select_related('room_type').order_by('room_number')

    def clean(self):
        cleaned = super().clean()
        check_in = cleaned.get('check_in')
        check_out = cleaned.get('check_out')
        if check_in and check_out and check_out <= check_in:
            raise forms.ValidationError("Check-out must be after check-in.")
        return cleaned


class RoomChargeForm(forms.ModelForm):
    class Meta:
        model = RoomCharge
        fields = ['description', 'amount']
        widgets = {
            'amount': forms.NumberInput(attrs={'step': '0.01', 'min': '0.01'}),
        }
