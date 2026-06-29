from django import forms
from .models import Payment, VendorPayment, Expense, BankAccount
from apps.bookkeeping.models import LedgerAccount
from apps.billing.models import Invoice
from apps.utils.nepali_date import NepaliDateWidget, NepaliDateField, FiscalYearDateMixin
from .services.payment_number_service import generate_payment_number


class BankAccountForm(forms.ModelForm):
    class Meta:
        model = BankAccount
        fields = ['bank_name', 'account_name', 'account_number', 'branch_name', 'is_active']
        widgets = {
            'bank_name':      forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Nepal Bank Ltd'}),
            'account_name':   forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Account holder name'}),
            'account_number': forms.TextInput(attrs={'class': 'form-control'}),
            'branch_name':    forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Optional'}),
        }


class PaymentForm(FiscalYearDateMixin, forms.ModelForm):
    date = NepaliDateField(widget=NepaliDateWidget(), required=True, label='Date (BS)')

    class Meta:
        model = Payment
        fields = ['payment_type', 'invoice', 'date', 'amount', 'discount_amount', 'method', 'bank_account', 'ledger_account', 'reference_number', 'description']
        widgets = {
            'amount':           forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'discount_amount':  forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'method':           forms.Select(attrs={'class': 'form-control'}),
            'bank_account':     forms.Select(attrs={'class': 'form-control'}),
            'payment_type':     forms.Select(attrs={'class': 'form-control'}),
            'reference_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter payment reference number'}),
            'description':      forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
        labels = {
            'reference_number': 'Payment Ref No',
            'date':             'Date (BS)',
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)

        if user and hasattr(user, 'company') and user.company:
            self.fields['ledger_account'].queryset = LedgerAccount.objects.filter(company=user.company)
            self.fields['invoice'].queryset = Invoice.objects.filter(company=user.company)
            self.fields['bank_account'].queryset = BankAccount.active_objects.filter(company=user.company, is_active=True)
        else:
            self.fields['ledger_account'].queryset = LedgerAccount.objects.none()
            self.fields['invoice'].queryset = Invoice.objects.none()
            self.fields['bank_account'].queryset = BankAccount.objects.none()

        self.fields['invoice'].required = False
        self.fields['ledger_account'].required = False
        self.fields['bank_account'].required = False
        self.fields['ledger_account'].help_text = "Required for expense, salary, and other payments"
        self.fields['bank_account'].help_text = "Select which bank account this payment was received into / sent from (Bank Transfer / Cheque)"
        self.fields['invoice'].help_text = "Optional — links payment to a specific invoice and reduces its outstanding balance"
        self.fields['reference_number'].help_text = "Enter a unique payment reference number"

        if not self.data.get('date') and not getattr(self.instance, 'pk', None):
            from apps.utils.nepali_date import today_bs
            self.fields['date'].initial = today_bs()
        self.inject_fiscal_year(self.request)
        
    def clean(self):
        cleaned_data = super().clean()
        payment_type = cleaned_data.get('payment_type')
        invoice = cleaned_data.get('invoice')
        ledger_account = cleaned_data.get('ledger_account')
        amount = cleaned_data.get('amount')

        # Validation based on payment type — invoice is optional for CUSTOMER
        # (journals to generic AR when no invoice; outstanding_balance untouched)

        if payment_type in ['EXPENSE', 'SALARY', 'OTHER'] and not ledger_account:
            raise forms.ValidationError("Ledger account is required for expense, salary, and other payments.")

        # Validate payment amount does not exceed invoice outstanding balance (only for customer payments)
        if payment_type == 'CUSTOMER' and invoice and amount:
            try:
                if hasattr(invoice, 'outstanding_balance') and amount > invoice.outstanding_balance:
                    raise forms.ValidationError(f"Payment amount cannot exceed the invoice's outstanding balance of {invoice.outstanding_balance}.")
            except (AttributeError, TypeError):
                # If there's an issue accessing outstanding_balance, skip this validation
                pass

        # Validate amount is positive
        if amount is not None and amount <= 0:
            raise forms.ValidationError("Payment amount must be greater than zero.")

        return cleaned_data


