from django import forms
from .models import Report
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