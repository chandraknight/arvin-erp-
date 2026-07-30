from django import forms
from .models import Report, AccountingPolicyNote, RelatedPartyTransaction, ContingentLiability
from apps.utils.nepali_date import NepaliDateWidget, NepaliDateField


class ReportForm(forms.ModelForm):
    start_date = NepaliDateField(widget=NepaliDateWidget(), required=False, label='Start Date (BS)')
    end_date = NepaliDateField(widget=NepaliDateWidget(), required=False, label='End Date (BS)')

    class Meta:
        model = Report
        fields = ['name', 'report_type', 'start_date', 'end_date']

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        if start_date and end_date and start_date > end_date:
            raise forms.ValidationError("End date must be after start date.")
        return cleaned_data
    

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['report_type'].choices = [
            ('sales', 'Sales'),
            ('inventory', 'Inventory'),
            ('stock_transactions', 'Stock Transactions'),
            ('billing', 'Billing'),
        ]


class AccountingPolicyNoteForm(forms.ModelForm):
    class Meta:
        model = AccountingPolicyNote
        fields = ['content']
        widgets = {
            'content': forms.Textarea(attrs={'rows': 14, 'class': 'w-full border border-gray-300 rounded-md text-sm px-3 py-2'}),
        }


class RelatedPartyTransactionForm(forms.ModelForm):
    transaction_date = NepaliDateField(widget=NepaliDateWidget(), label='Transaction Date (BS)')

    class Meta:
        model = RelatedPartyTransaction
        fields = ['party_name', 'relationship', 'transaction_date', 'nature_of_transaction', 'amount', 'outstanding_balance', 'remarks']
        widgets = {
            'party_name': forms.TextInput(attrs={'class': 'border border-gray-300 rounded-md text-sm px-3 py-2 w-full'}),
            'relationship': forms.TextInput(attrs={'class': 'border border-gray-300 rounded-md text-sm px-3 py-2 w-full'}),
            'nature_of_transaction': forms.TextInput(attrs={'class': 'border border-gray-300 rounded-md text-sm px-3 py-2 w-full'}),
            'amount': forms.NumberInput(attrs={'step': '0.01', 'class': 'border border-gray-300 rounded-md text-sm px-3 py-2 w-full'}),
            'outstanding_balance': forms.NumberInput(attrs={'step': '0.01', 'class': 'border border-gray-300 rounded-md text-sm px-3 py-2 w-full'}),
            'remarks': forms.Textarea(attrs={'rows': 2, 'class': 'border border-gray-300 rounded-md text-sm px-3 py-2 w-full'}),
        }


class ContingentLiabilityForm(forms.ModelForm):
    as_of_date = NepaliDateField(widget=NepaliDateWidget(), label='As Of Date (BS)')

    class Meta:
        model = ContingentLiability
        fields = ['description', 'nature', 'estimated_amount', 'status', 'as_of_date', 'remarks']
        widgets = {
            'description': forms.TextInput(attrs={'class': 'border border-gray-300 rounded-md text-sm px-3 py-2 w-full'}),
            'nature': forms.TextInput(attrs={'class': 'border border-gray-300 rounded-md text-sm px-3 py-2 w-full'}),
            'estimated_amount': forms.NumberInput(attrs={'step': '0.01', 'class': 'border border-gray-300 rounded-md text-sm px-3 py-2 w-full'}),
            'status': forms.Select(attrs={'class': 'border border-gray-300 rounded-md text-sm px-3 py-2 w-full'}),
            'remarks': forms.Textarea(attrs={'rows': 2, 'class': 'border border-gray-300 rounded-md text-sm px-3 py-2 w-full'}),
        }