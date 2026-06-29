from django import forms
from apps.vendors.models import Vendor
from apps.utils.constant import JOURNAL_ENTRY_TYPES


class VendorForm(forms.ModelForm):
    # Add opening balance fields
    opening_balance_amount = forms.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        initial=0.00,
        required=False,
        help_text="Opening balance amount for this vendor (from last year's closing balance)"
    )
    opening_balance_type = forms.ChoiceField(
        choices=JOURNAL_ENTRY_TYPES,
        initial='CREDIT',
        required=False,
        help_text="Payables are typically CREDIT balances"
    )
    
    class Meta:
        model = Vendor
        fields = ['name', 'contact_person', 'email', 'phone', 'address', 'pan_number']
        widgets = {
            'address': forms.Textarea(attrs={'rows': 1}),
            'name': forms.TextInput(attrs={'placeholder': 'Enter vendor name'}),
            'phone': forms.TextInput(attrs={'placeholder': 'Enter phone number'}),
            'contact_person': forms.TextInput(attrs={'placeholder': 'Enter Contact Person Name'}),
            'pan_number': forms.TextInput(attrs={'placeholder': 'e.g. 123456789'}),
        }
        labels = {
            'name': 'Vendor Name',
            'contact_person': 'Contact',
            'email': 'Email',
            'phone': 'Phone',
            'address': 'Address',
            'pan_number': 'PAN Number',
        }
        help_texts = {
            'phone': 'Enter with country code (e.g. +977...)',
            'email': 'Valid email address required',
            'pan_number': 'PAN / VAT number (optional)',
        }

    def __init__(self, *args, **kwargs):
        kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
