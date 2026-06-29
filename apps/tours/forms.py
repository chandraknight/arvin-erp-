from django import forms
from .models import (
    TourDestination, TourPackage, TourEnquiry, TourBooking, TourBookingItem,
    IATAAirline, IATAAirport, AirTicket, IATASourceFile, AIRFile, BSPPaymentRecord,
)


class TourDestinationForm(forms.ModelForm):
    class Meta:
        model = TourDestination
        fields = ['name', 'country', 'description', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'block w-full border border-gray-300 px-4 py-3 text-gray-900 focus:outline-none focus:ring-2 focus:ring-green-600 focus:border-green-600 transition duration-150'}),
            'country': forms.TextInput(attrs={'class': 'block w-full border border-gray-300 px-4 py-3 text-gray-900 focus:outline-none focus:ring-2 focus:ring-green-600 focus:border-green-600 transition duration-150'}),
            'description': forms.Textarea(attrs={'rows': 3, 'class': 'block w-full border border-gray-300 px-4 py-3 text-gray-900 focus:outline-none focus:ring-2 focus:ring-green-600 focus:border-green-600 transition duration-150'}),
        }


class TourPackageForm(forms.ModelForm):
    class Meta:
        model = TourPackage
        fields = [
            'destination', 'name', 'package_type',
            'duration_days', 'duration_nights',
            'price_per_adult', 'price_per_child',
            'max_capacity', 'inclusions', 'exclusions',
            'description', 'is_active',
        ]
        widgets = {
            'destination': forms.Select(attrs={'class': 'block w-full border border-gray-300 px-4 py-3 text-gray-900 focus:outline-none focus:ring-2 focus:ring-green-600 focus:border-green-600 transition duration-150'}),
            'name': forms.TextInput(attrs={'class': 'block w-full border border-gray-300 px-4 py-3 text-gray-900 focus:outline-none focus:ring-2 focus:ring-green-600 focus:border-green-600 transition duration-150'}),
            'package_type': forms.Select(attrs={'class': 'block w-full border border-gray-300 px-4 py-3 text-gray-900 focus:outline-none focus:ring-2 focus:ring-green-600 focus:border-green-600 transition duration-150'}),
            'duration_days': forms.NumberInput(attrs={'class': 'block w-full border border-gray-300 px-4 py-3 text-gray-900 focus:outline-none focus:ring-2 focus:ring-green-600 focus:border-green-600 transition duration-150', 'min': 1}),
            'duration_nights': forms.NumberInput(attrs={'class': 'block w-full border border-gray-300 px-4 py-3 text-gray-900 focus:outline-none focus:ring-2 focus:ring-green-600 focus:border-green-600 transition duration-150', 'min': 0}),
            'price_per_adult': forms.NumberInput(attrs={'class': 'block w-full border border-gray-300 px-4 py-3 text-gray-900 focus:outline-none focus:ring-2 focus:ring-green-600 focus:border-green-600 transition duration-150', 'step': '0.01'}),
            'price_per_child': forms.NumberInput(attrs={'class': 'block w-full border border-gray-300 px-4 py-3 text-gray-900 focus:outline-none focus:ring-2 focus:ring-green-600 focus:border-green-600 transition duration-150', 'step': '0.01'}),
            'max_capacity': forms.NumberInput(attrs={'class': 'block w-full border border-gray-300 px-4 py-3 text-gray-900 focus:outline-none focus:ring-2 focus:ring-green-600 focus:border-green-600 transition duration-150', 'min': 1}),
            'inclusions': forms.Textarea(attrs={'rows': 4, 'class': 'block w-full border border-gray-300 px-4 py-3 text-gray-900 focus:outline-none focus:ring-2 focus:ring-green-600 focus:border-green-600 transition duration-150', 'placeholder': 'Airfare\nHotel accommodation\nBreakfast daily'}),
            'exclusions': forms.Textarea(attrs={'rows': 4, 'class': 'block w-full border border-gray-300 px-4 py-3 text-gray-900 focus:outline-none focus:ring-2 focus:ring-green-600 focus:border-green-600 transition duration-150', 'placeholder': 'Visa fees\nPersonal expenses\nTravel insurance'}),
            'description': forms.Textarea(attrs={'rows': 3, 'class': 'block w-full border border-gray-300 px-4 py-3 text-gray-900 focus:outline-none focus:ring-2 focus:ring-green-600 focus:border-green-600 transition duration-150'}),
        }

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company:
            self.fields['destination'].queryset = TourDestination.active_objects.filter(company=company, is_active=True)


class TourEnquiryForm(forms.ModelForm):
    class Meta:
        model = TourEnquiry
        fields = [
            'customer', 'contact_name', 'contact_phone', 'contact_email',
            'package', 'destination', 'travel_date', 'return_date',
            'num_adults', 'num_children',
            'source', 'special_requests', 'internal_notes', 'assigned_to',
        ]
        widgets = {
            'customer': forms.Select(attrs={'class': 'block w-full border border-gray-300 px-4 py-3 text-gray-900 focus:outline-none focus:ring-2 focus:ring-green-600 focus:border-green-600 transition duration-150'}),
            'contact_name': forms.TextInput(attrs={'class': 'block w-full border border-gray-300 px-4 py-3 text-gray-900 focus:outline-none focus:ring-2 focus:ring-green-600 focus:border-green-600 transition duration-150'}),
            'contact_phone': forms.TextInput(attrs={'class': 'block w-full border border-gray-300 px-4 py-3 text-gray-900 focus:outline-none focus:ring-2 focus:ring-green-600 focus:border-green-600 transition duration-150'}),
            'contact_email': forms.EmailInput(attrs={'class': 'block w-full border border-gray-300 px-4 py-3 text-gray-900 focus:outline-none focus:ring-2 focus:ring-green-600 focus:border-green-600 transition duration-150'}),
            'package': forms.Select(attrs={'class': 'block w-full border border-gray-300 px-4 py-3 text-gray-900 focus:outline-none focus:ring-2 focus:ring-green-600 focus:border-green-600 transition duration-150'}),
            'destination': forms.Select(attrs={'class': 'block w-full border border-gray-300 px-4 py-3 text-gray-900 focus:outline-none focus:ring-2 focus:ring-green-600 focus:border-green-600 transition duration-150'}),
            'travel_date': forms.DateInput(attrs={'type': 'text', 'class': 'flatpickr block w-full border border-gray-300 px-4 py-3 text-gray-900 focus:outline-none focus:ring-2 focus:ring-green-600 focus:border-green-600 transition duration-150'}),
            'return_date': forms.DateInput(attrs={'type': 'text', 'class': 'flatpickr block w-full border border-gray-300 px-4 py-3 text-gray-900 focus:outline-none focus:ring-2 focus:ring-green-600 focus:border-green-600 transition duration-150'}),
            'num_adults': forms.NumberInput(attrs={'class': 'block w-full border border-gray-300 px-4 py-3 text-gray-900 focus:outline-none focus:ring-2 focus:ring-green-600 focus:border-green-600 transition duration-150', 'min': 1}),
            'num_children': forms.NumberInput(attrs={'class': 'block w-full border border-gray-300 px-4 py-3 text-gray-900 focus:outline-none focus:ring-2 focus:ring-green-600 focus:border-green-600 transition duration-150', 'min': 0}),
            'source': forms.Select(attrs={'class': 'block w-full border border-gray-300 px-4 py-3 text-gray-900 focus:outline-none focus:ring-2 focus:ring-green-600 focus:border-green-600 transition duration-150'}),
            'special_requests': forms.Textarea(attrs={'rows': 3, 'class': 'block w-full border border-gray-300 px-4 py-3 text-gray-900 focus:outline-none focus:ring-2 focus:ring-green-600 focus:border-green-600 transition duration-150'}),
            'internal_notes': forms.Textarea(attrs={'rows': 3, 'class': 'block w-full border border-gray-300 px-4 py-3 text-gray-900 focus:outline-none focus:ring-2 focus:ring-green-600 focus:border-green-600 transition duration-150'}),
            'assigned_to': forms.Select(attrs={'class': 'block w-full border border-gray-300 px-4 py-3 text-gray-900 focus:outline-none focus:ring-2 focus:ring-green-600 focus:border-green-600 transition duration-150'}),
        }

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company:
            self.fields['customer'].queryset = self.fields['customer'].queryset.filter(company=company)
            self.fields['package'].queryset = TourPackage.active_objects.filter(company=company, is_active=True)
            self.fields['destination'].queryset = TourDestination.active_objects.filter(company=company, is_active=True)
        self.fields['customer'].required = False
        self.fields['package'].required = False
        self.fields['destination'].required = False


class TourBookingForm(forms.ModelForm):
    class Meta:
        model = TourBooking
        fields = [
            'customer', 'contact_name', 'contact_phone', 'contact_email',
            'travel_date', 'return_date',
            'num_adults', 'num_children',
            'discount_amount', 'tax_percent',
            'special_requests', 'internal_notes', 'assigned_to',
        ]
        widgets = {
            'customer': forms.Select(attrs={'class': 'block w-full border border-gray-300 px-4 py-3 text-gray-900 focus:outline-none focus:ring-2 focus:ring-green-600 focus:border-green-600 transition duration-150'}),
            'contact_name': forms.TextInput(attrs={'class': 'block w-full border border-gray-300 px-4 py-3 text-gray-900 focus:outline-none focus:ring-2 focus:ring-green-600 focus:border-green-600 transition duration-150'}),
            'contact_phone': forms.TextInput(attrs={'class': 'block w-full border border-gray-300 px-4 py-3 text-gray-900 focus:outline-none focus:ring-2 focus:ring-green-600 focus:border-green-600 transition duration-150'}),
            'contact_email': forms.EmailInput(attrs={'class': 'block w-full border border-gray-300 px-4 py-3 text-gray-900 focus:outline-none focus:ring-2 focus:ring-green-600 focus:border-green-600 transition duration-150'}),
            'travel_date': forms.DateInput(attrs={'type': 'text', 'class': 'flatpickr block w-full border border-gray-300 px-4 py-3 text-gray-900 focus:outline-none focus:ring-2 focus:ring-green-600 focus:border-green-600 transition duration-150'}),
            'return_date': forms.DateInput(attrs={'type': 'text', 'class': 'flatpickr block w-full border border-gray-300 px-4 py-3 text-gray-900 focus:outline-none focus:ring-2 focus:ring-green-600 focus:border-green-600 transition duration-150'}),
            'num_adults': forms.NumberInput(attrs={'class': 'block w-full border border-gray-300 px-4 py-3 text-gray-900 focus:outline-none focus:ring-2 focus:ring-green-600 focus:border-green-600 transition duration-150', 'min': 1}),
            'num_children': forms.NumberInput(attrs={'class': 'block w-full border border-gray-300 px-4 py-3 text-gray-900 focus:outline-none focus:ring-2 focus:ring-green-600 focus:border-green-600 transition duration-150', 'min': 0}),
            'discount_amount': forms.NumberInput(attrs={'class': 'block w-full border border-gray-300 px-4 py-3 text-gray-900 focus:outline-none focus:ring-2 focus:ring-green-600 focus:border-green-600 transition duration-150', 'step': '0.01', 'min': 0}),
            'tax_percent': forms.NumberInput(attrs={'class': 'block w-full border border-gray-300 px-4 py-3 text-gray-900 focus:outline-none focus:ring-2 focus:ring-green-600 focus:border-green-600 transition duration-150', 'step': '0.01', 'min': 0}),
            'special_requests': forms.Textarea(attrs={'rows': 3, 'class': 'block w-full border border-gray-300 px-4 py-3 text-gray-900 focus:outline-none focus:ring-2 focus:ring-green-600 focus:border-green-600 transition duration-150'}),
            'internal_notes': forms.Textarea(attrs={'rows': 3, 'class': 'block w-full border border-gray-300 px-4 py-3 text-gray-900 focus:outline-none focus:ring-2 focus:ring-green-600 focus:border-green-600 transition duration-150'}),
            'assigned_to': forms.Select(attrs={'class': 'block w-full border border-gray-300 px-4 py-3 text-gray-900 focus:outline-none focus:ring-2 focus:ring-green-600 focus:border-green-600 transition duration-150'}),
        }

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company:
            self.fields['customer'].queryset = self.fields['customer'].queryset.filter(company=company)
        self.fields['customer'].required = False


class TourBookingItemForm(forms.ModelForm):
    class Meta:
        model = TourBookingItem
        fields = ['item_type', 'package', 'description', 'quantity', 'unit_price', 'discount_percent']
        widgets = {
            'item_type': forms.Select(attrs={'class': 'block w-full border border-gray-300 px-3 py-2 text-gray-900 focus:outline-none focus:ring-2 focus:ring-green-600 focus:border-green-600 transition duration-150 text-sm'}),
            'package': forms.Select(attrs={'class': 'block w-full border border-gray-300 px-3 py-2 text-gray-900 focus:outline-none focus:ring-2 focus:ring-green-600 focus:border-green-600 transition duration-150 text-sm'}),
            'description': forms.TextInput(attrs={'class': 'block w-full border border-gray-300 px-3 py-2 text-gray-900 focus:outline-none focus:ring-2 focus:ring-green-600 focus:border-green-600 transition duration-150 text-sm'}),
            'quantity': forms.NumberInput(attrs={'class': 'block w-full border border-gray-300 px-3 py-2 text-gray-900 focus:outline-none focus:ring-2 focus:ring-green-600 focus:border-green-600 transition duration-150 text-sm', 'min': 1}),
            'unit_price': forms.NumberInput(attrs={'class': 'block w-full border border-gray-300 px-3 py-2 text-gray-900 focus:outline-none focus:ring-2 focus:ring-green-600 focus:border-green-600 transition duration-150 text-sm', 'step': '0.01', 'min': 0}),
            'discount_percent': forms.NumberInput(attrs={'class': 'block w-full border border-gray-300 px-3 py-2 text-gray-900 focus:outline-none focus:ring-2 focus:ring-green-600 focus:border-green-600 transition duration-150 text-sm', 'step': '0.01', 'min': 0, 'max': 100}),
        }

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company:
            self.fields['package'].queryset = TourPackage.active_objects.filter(company=company, is_active=True)
        self.fields['package'].required = False


TourBookingItemFormSet = forms.inlineformset_factory(
    TourBooking, TourBookingItem,
    form=TourBookingItemForm,
    extra=1, can_delete=True,
    fields=['item_type', 'package', 'description', 'quantity', 'unit_price', 'discount_percent'],
)

_INPUT = 'block w-full border border-gray-300 px-4 py-3 text-gray-900 focus:outline-none focus:ring-2 focus:ring-green-600 focus:border-green-600 transition duration-150'
_INPUT_SM = 'block w-full border border-gray-300 px-3 py-2 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-green-600 focus:border-green-600 transition duration-150'


class AirTicketForm(forms.ModelForm):
    class Meta:
        model = AirTicket
        fields = [
            'booking', 'ticket_number', 'pnr', 'conjunction_tickets',
            'passenger_name', 'passenger_type',
            'airline', 'validating_carrier', 'origin', 'destination',
            'routing', 'trip_type', 'cabin', 'fare_basis',
            'issue_date', 'departure_date', 'return_date',
            'fare_amount', 'tax_amount', 'fuel_surcharge', 'gross_fare',
            'commission_percent', 'commission_amount', 'net_fare',
            'bsp_reference', 'status', 'remarks',
        ]
        widgets = {
            'booking': forms.Select(attrs={'class': _INPUT}),
            'ticket_number': forms.TextInput(attrs={'class': _INPUT, 'placeholder': '157-2345678901'}),
            'pnr': forms.TextInput(attrs={'class': _INPUT, 'placeholder': 'ABC123'}),
            'conjunction_tickets': forms.TextInput(attrs={'class': _INPUT}),
            'passenger_name': forms.TextInput(attrs={'class': _INPUT, 'placeholder': 'SMITH/JOHN MR'}),
            'passenger_type': forms.TextInput(attrs={'class': _INPUT}),
            'airline': forms.Select(attrs={'class': _INPUT}),
            'validating_carrier': forms.TextInput(attrs={'class': _INPUT, 'maxlength': 3, 'placeholder': 'QR'}),
            'origin': forms.Select(attrs={'class': _INPUT}),
            'destination': forms.Select(attrs={'class': _INPUT}),
            'routing': forms.TextInput(attrs={'class': _INPUT, 'placeholder': 'KTM-DEL-DXB-DEL-KTM'}),
            'trip_type': forms.Select(attrs={'class': _INPUT}),
            'cabin': forms.Select(attrs={'class': _INPUT}),
            'fare_basis': forms.TextInput(attrs={'class': _INPUT}),
            'issue_date': forms.DateInput(attrs={'type': 'text', 'class': f'flatpickr {_INPUT}'}),
            'departure_date': forms.DateInput(attrs={'type': 'text', 'class': f'flatpickr {_INPUT}'}),
            'return_date': forms.DateInput(attrs={'type': 'text', 'class': f'flatpickr {_INPUT}'}),
            'fare_amount': forms.NumberInput(attrs={'class': _INPUT, 'step': '0.01', 'min': 0}),
            'tax_amount': forms.NumberInput(attrs={'class': _INPUT, 'step': '0.01', 'min': 0}),
            'fuel_surcharge': forms.NumberInput(attrs={'class': _INPUT, 'step': '0.01', 'min': 0}),
            'gross_fare': forms.NumberInput(attrs={'class': _INPUT, 'step': '0.01', 'min': 0}),
            'commission_percent': forms.NumberInput(attrs={'class': _INPUT, 'step': '0.01', 'min': 0}),
            'commission_amount': forms.NumberInput(attrs={'class': _INPUT, 'step': '0.01', 'min': 0}),
            'net_fare': forms.NumberInput(attrs={'class': _INPUT, 'step': '0.01', 'min': 0}),
            'bsp_reference': forms.TextInput(attrs={'class': _INPUT}),
            'status': forms.Select(attrs={'class': _INPUT}),
            'remarks': forms.Textarea(attrs={'rows': 2, 'class': _INPUT}),
        }

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company:
            self.fields['booking'].queryset = TourBooking.active_objects.filter(company=company)
        self.fields['booking'].required = False
        self.fields['airline'].required = False
        self.fields['origin'].required = False
        self.fields['destination'].required = False


class IATASourceFileForm(forms.ModelForm):
    _IATA_ALLOWED = ['csv', 'xlsx', 'xls']

    class Meta:
        model = IATASourceFile
        fields = ['file', 'period_from', 'period_to', 'description']
        widgets = {
            'file': forms.FileInput(attrs={'class': _INPUT, 'accept': '.csv,.xlsx,.xls'}),
            'period_from': forms.DateInput(attrs={'type': 'text', 'class': f'flatpickr {_INPUT}'}),
            'period_to': forms.DateInput(attrs={'type': 'text', 'class': f'flatpickr {_INPUT}'}),
            'description': forms.TextInput(attrs={'class': _INPUT, 'placeholder': 'e.g. BSP Nepal May 2026 Week 1'}),
        }

    def clean_file(self):
        f = self.cleaned_data.get('file')
        if f:
            ext = f.name.rsplit('.', 1)[-1].lower() if '.' in f.name else ''
            if ext not in self._IATA_ALLOWED:
                raise forms.ValidationError(f"Unsupported file type. Allowed: {', '.join(self._IATA_ALLOWED)}")
        return f


class IATAAirlineForm(forms.ModelForm):
    class Meta:
        model = IATAAirline
        fields = ['iata_code', 'icao_code', 'name', 'country', 'is_active']
        widgets = {f: forms.TextInput(attrs={'class': _INPUT}) for f in ['iata_code', 'icao_code', 'name', 'country']}


class IATAAirportForm(forms.ModelForm):
    class Meta:
        model = IATAAirport
        fields = ['iata_code', 'icao_code', 'name', 'city', 'country', 'country_code', 'is_active']
        widgets = {f: forms.TextInput(attrs={'class': _INPUT}) for f in ['iata_code', 'icao_code', 'name', 'city', 'country', 'country_code']}


class AIRFileForm(forms.ModelForm):
    _AIR_ALLOWED = ['air', 'txt', 'csv', 'xlsx', 'xls']

    class Meta:
        model = AIRFile
        fields = [
            'file', 'original_filename', 'billing_reference',
            'period_from', 'period_to', 'payment_due_date',
            'total_sales', 'total_refunds', 'total_commission', 'total_taxes', 'net_amount_due',
            'bsp_source_file', 'description', 'notes',
        ]
        widgets = {
            'file':              forms.FileInput(attrs={'class': _INPUT, 'accept': '.air,.txt,.csv,.xlsx,.xls'}),
            'original_filename': forms.TextInput(attrs={'class': _INPUT, 'placeholder': 'auto-filled from file'}),
            'billing_reference': forms.TextInput(attrs={'class': _INPUT, 'placeholder': 'BSP billing / remittance reference'}),
            'period_from':       forms.DateInput(attrs={'type': 'text', 'class': f'flatpickr {_INPUT}'}),
            'period_to':         forms.DateInput(attrs={'type': 'text', 'class': f'flatpickr {_INPUT}'}),
            'payment_due_date':  forms.DateInput(attrs={'type': 'text', 'class': f'flatpickr {_INPUT}'}),
            'total_sales':       forms.NumberInput(attrs={'class': _INPUT, 'step': '0.01', 'min': 0}),
            'total_refunds':     forms.NumberInput(attrs={'class': _INPUT, 'step': '0.01', 'min': 0}),
            'total_commission':  forms.NumberInput(attrs={'class': _INPUT, 'step': '0.01', 'min': 0}),
            'total_taxes':       forms.NumberInput(attrs={'class': _INPUT, 'step': '0.01', 'min': 0}),
            'net_amount_due':    forms.NumberInput(attrs={'class': _INPUT, 'step': '0.01', 'min': 0}),
            'bsp_source_file':   forms.Select(attrs={'class': _INPUT}),
            'description':       forms.TextInput(attrs={'class': _INPUT}),
            'notes':             forms.Textarea(attrs={'rows': 3, 'class': _INPUT}),
        }

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['file'].required = False
        self.fields['original_filename'].required = False
        if company:
            self.fields['bsp_source_file'].queryset = IATASourceFile.objects.filter(company=company)
        else:
            self.fields['bsp_source_file'].queryset = IATASourceFile.objects.none()
        self.fields['bsp_source_file'].required = False

    def clean_file(self):
        f = self.cleaned_data.get('file')
        if f:
            ext = f.name.rsplit('.', 1)[-1].lower() if '.' in f.name else ''
            if ext not in self._AIR_ALLOWED:
                raise forms.ValidationError(f"Unsupported file type. Allowed: {', '.join(self._AIR_ALLOWED)}")
        return f


class BSPPaymentForm(forms.ModelForm):
    class Meta:
        model = BSPPaymentRecord
        fields = ['payment_date', 'amount', 'payment_method', 'bank_reference', 'notes']
        widgets = {
            'payment_date':   forms.DateInput(attrs={'type': 'text', 'class': f'flatpickr {_INPUT}'}),
            'amount':         forms.NumberInput(attrs={'class': _INPUT, 'step': '0.01', 'min': 0}),
            'payment_method': forms.Select(attrs={'class': _INPUT}),
            'bank_reference': forms.TextInput(attrs={'class': _INPUT, 'placeholder': 'Bank transaction / cheque ref'}),
            'notes':          forms.Textarea(attrs={'rows': 2, 'class': _INPUT}),
        }
