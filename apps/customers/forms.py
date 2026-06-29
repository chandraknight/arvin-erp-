from django import forms
from .models import Customer
from apps.utils.constant import JOURNAL_ENTRY_TYPES

class CustomerForm(forms.ModelForm):
    # Add opening balance fields
    opening_balance_amount = forms.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        initial=0.00,
        required=False,
        help_text="Opening balance amount for this customer (from last year's closing balance)"
    )
    opening_balance_type = forms.ChoiceField(
        choices=JOURNAL_ENTRY_TYPES,
        initial='DEBIT',
        required=False,
        help_text="Receivables are typically DEBIT balances"
    )
    
    class Meta:
        model = Customer
        fields = ['company', 'name', 'email', 'phone', 'address', 'text']
        labels = {
            'text': 'Notes',
        }
        widgets = {
            'address': forms.TextInput(attrs={'maxlength': 200, 'class': 'w-full'}),
            'text': forms.Textarea(attrs={'rows': 3, 'class': 'w-full md:col-span-2'}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        if not (user and user.is_superuser):
            self.fields.pop('company', None)

        self.fields['address'].widget = forms.TextInput(attrs={'maxlength': 200})

    def clean_phone(self):
        return self.cleaned_data.get('phone') or None

    def clean_email(self):
        return self.cleaned_data.get('email') or None