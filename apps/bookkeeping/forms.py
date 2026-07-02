from django import forms
from django.forms import inlineformset_factory
from .models import JournalEntry, JournalEntryLine, LedgerAccount, LedgerOpeningBalance
from django.forms import BaseInlineFormSet
from django.db import models
from apps.utils.nepali_date import NepaliDateWidget, NepaliDateField, FiscalYearDateMixin


class RequestJournalEntryInlineFormSet(BaseInlineFormSet):
    def __init__(self, *args, request=None, **kwargs):
        self.request = request
        super().__init__(*args, **kwargs)

    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        kwargs['request'] = self.request
        return kwargs


class JournalEntryForm(FiscalYearDateMixin, forms.ModelForm):
    date = NepaliDateField(
        widget=NepaliDateWidget(),
        required=True,
        label='Date (BS)',
    )

    class Meta:
        model = JournalEntry
        fields = ['company', 'date', 'description']

    def __init__(self, *args, request=None, **kwargs):
        self.request = request
        super().__init__(*args, **kwargs)

        self.fields['company'].initial = self.request.user.company
        self.fields['company'].disabled = True
        if self.request.user.is_superuser:
            self.fields['company'].disabled = False

        self.inject_fiscal_year(self.request)


class JournalEntryLineForm(forms.ModelForm):
    debit_amount = forms.DecimalField(
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'form-control debit-input',
            'placeholder': 'Debit Amount'
        })
    )
    credit_amount = forms.DecimalField(
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'form-control credit-input',
            'placeholder': 'Credit Amount'
        })
    )

    narration = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control narration-input',
            'placeholder': 'Enter Narration'
        })
    )

    class Meta:
        model = JournalEntryLine
        fields = ['account', 'narration']

    def __init__(self, *args, request=None, **kwargs):
        self.request = request
        super().__init__(*args, **kwargs)

        self.fields['account'].widget.attrs.update({'class': 'form-select'})
        self.fields['narration'].widget.attrs.update({'class': 'form-control'})

        if self.request:
            self.fields['account'].queryset = self.fields['account'].queryset.filter(
                company=self.request.user.company
            ).order_by(
                models.F('parent_account').asc(nulls_first=True),
                'name'  # Then alphabetically by name
            )

        if self.instance.pk:
            if self.instance.entry_type == 'DEBIT':
                self.fields['debit_amount'].initial = self.instance.amount
            else:
                self.fields['credit_amount'].initial = self.instance.amount

    def clean(self):
        cleaned_data = super().clean()
        debit_amount = cleaned_data.get('debit_amount')
        credit_amount = cleaned_data.get('credit_amount')

        if debit_amount and credit_amount:
            raise forms.ValidationError("You can only enter either a debit or credit amount, not both.")

        if not debit_amount and not credit_amount:
            raise forms.ValidationError("You must enter either a debit or credit amount.")

        if debit_amount:
            cleaned_data['amount'] = debit_amount
            cleaned_data['entry_type'] = 'DEBIT'
        else:
            cleaned_data['amount'] = credit_amount
            cleaned_data['entry_type'] = 'CREDIT'

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.amount = self.cleaned_data['amount']
        instance.entry_type = self.cleaned_data['entry_type']

        if commit:
            instance.save()
        return instance

JournalEntryLineFormSet = inlineformset_factory(
    JournalEntry,
    JournalEntryLine,
    form=JournalEntryLineForm,
    formset=RequestJournalEntryInlineFormSet,
    extra=2,
    can_delete=True
)


class LedgerAccountForm(forms.ModelForm):
    class Meta:
        model = LedgerAccount
        fields = ['company', 'name', 'account_type', 'code', 'parent_account']
        widgets = {
            'company': forms.Select(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'account_type': forms.Select(attrs={
                'class': 'form-control',
                'onchange': 'filterParentAccounts()'
            }),
            'code': forms.TextInput(attrs={'class': 'form-control'}),
            'parent_account': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        self.company = kwargs.pop('company', None)
        super().__init__(*args, **kwargs)

        if self.company:
            self.fields['company'].initial = self.company
            self.fields['company'].disabled = True
            self.fields['company'].widget.attrs['readonly'] = True

            qs = LedgerAccount.active_objects.filter(
                company=self.company,
                parent_account__isnull=True
            )
            self.fields['parent_account'].queryset = qs

            if self.instance and self.instance.pk:
                self.fields['parent_account'].queryset = qs.exclude(pk=self.instance.pk)

    def clean_code(self):
        code = self.cleaned_data.get('code')
        return code.strip() or None if isinstance(code, str) else code
