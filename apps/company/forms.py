from django import forms
from .models import Company, Branch, FiscalYear, ORGANISATION_TYPE_CHOICES
import nepali_datetime
import re


class CompanyForm(forms.ModelForm):
    class Meta:
        model = Company
        fields = [
            'name', 'address', 'phone', 'email', 'logo', 'tax_rate',
            'organisation_type',
            'vat_registered', 'vat_number', 'vat_inclusive',
            'enable_branch_accounting', 'enable_project_tracking', 'enable_forecasting',
            'enable_order_management', 'enable_manufacturing',
            'enable_hr_payroll', 'enable_purchasing', 'enable_inventory',
            'enable_restaurant', 'enable_pos', 'enable_tours', 'enable_ecom',
        ]
        widgets = {
            'address': forms.Textarea(attrs={'rows': 2}),
            'organisation_type': forms.Select(attrs={'class': 'form-control'}),
        }
        help_texts = {
            'vat_registered': 'Check if this company is registered for VAT/PAN.',
            'vat_inclusive': 'Check if prices already include VAT.',
            'enable_branch_accounting': 'Enables branch selection on invoices and branch-wise reports.',
            'enable_project_tracking': 'Enables the Projects & Cost Centres module.',
            'enable_forecasting': 'Enables Budget and Forecast module.',
            'enable_order_management': 'Enables Sales Orders and Delivery Management module.',
            'enable_manufacturing': 'Enables Manufacturing module (BOM, Work Orders, Production Runs).',
            'enable_hr_payroll': 'Enables HR & Payroll module (Employees, Attendance, Payroll Runs).',
            'enable_purchasing': 'Enables Purchasing module (Purchase Orders, Vendor Bills).',
            'enable_inventory': 'Enables Inventory / Product management module.',
            'enable_restaurant': 'Enables Restaurant module (Tables, KOT/BOT, Dining Orders, Printer Stations).',
            'enable_pos': 'Enables Point of Sale (POS) module for quick retail/counter sales.',
            'enable_tours': 'Enables Tours & Ticketing module (Enquiries, Bookings, Invoicing).',
            'enable_ecom': 'Enables E-Commerce storefront (/store/). Customers can browse and place COD orders online.',
        }

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        # tax_rate has a model default (13.00) — allow blank in the form
        self.fields['tax_rate'].required = False
        self.fields['tax_rate'].initial = '13.00'

    def clean_tax_rate(self):
        from decimal import Decimal
        val = self.cleaned_data.get('tax_rate')
        if val is None or val == '':
            return Decimal('13.00')
        return val


class CompanyBasicInfoForm(forms.ModelForm):
    """
    Restricted update form for company admins.
    Only basic contact info — VAT/tax fields are superuser-only.
    """
    class Meta:
        model = Company
        fields = [
            'name', 'address', 'phone', 'email', 'logo',
        ]
        widgets = {
            'address': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)


class CompanyAdminUserForm(forms.Form):
    """
    Sub-form used in the company creation wizard to create/assign an admin user.
    """
    admin_email = forms.EmailField(
        label='Admin Email',
        widget=forms.EmailInput(attrs={'placeholder': 'admin@company.com', 'autocomplete': 'off'}),
    )
    admin_first_name = forms.CharField(label='First Name', max_length=150)
    admin_last_name  = forms.CharField(label='Last Name',  max_length=150, required=False)
    admin_password   = forms.CharField(
        label='Password',
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
        min_length=8,
        help_text='Minimum 8 characters.',
    )
    admin_password_confirm = forms.CharField(
        label='Confirm Password',
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
    )

    def clean(self):
        cleaned = super().clean()
        pw  = cleaned.get('admin_password')
        pw2 = cleaned.get('admin_password_confirm')
        if pw and pw2 and pw != pw2:
            raise forms.ValidationError('Passwords do not match.')
        return cleaned


class BranchForm(forms.ModelForm):
    class Meta:
        phone = forms.CharField(
            max_length=20,
            required=False,
            widget=forms.TextInput(attrs={
                'placeholder': 'Enter numbers or hyphens only',
                'pattern': '^[0-9-]*$',
                'maxlength': '20'
            }),
            help_text="Only numbers and hyphens are allowed"
        )
        model = Branch
        fields = ['company', 'name', 'address', 'phone', 'email', 'is_main_branch']
        widgets = {
            'address': forms.Textarea(attrs={'rows': 1}),

        }


    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)

        if self.request and not self.request.user.is_superuser:
            if 'company' in self.fields:
                del self.fields['company']
            if hasattr(self, 'instance'):
                self.instance.company = self.request.user.company

        if self.instance and self.instance.pk and self.instance.is_main_branch:
            company_branches = self.instance.company.branches.exclude(pk=self.instance.pk)
            if not company_branches.exists():
                self.fields['is_main_branch'].disabled = True
                self.fields['is_main_branch'].help_text = "This is the only branch, it must be the main branch."

    def clean(self):
        cleaned_data = super().clean()

        if self.request and not self.request.user.is_superuser:
            cleaned_data['company'] = self.request.user.company

        return cleaned_data

    def clean_phone(self):
        phone = self.cleaned_data.get('phone')
        if phone:
            phone = phone.replace(' ', '')

            if not all(c.isdigit() or c == '-' for c in phone):
                raise forms.ValidationError("Phone number can only contain numbers and hyphens")

            digit_count = sum(c.isdigit() for c in phone)
            if digit_count < 7:
                raise forms.ValidationError("Phone number must contain at least 7 digits")
            if digit_count > 14:
                raise forms.ValidationError("Phone number cannot exceed 14 digits")

        return phone

    def clean_is_main_branch(self):
        is_main_branch = self.cleaned_data.get('is_main_branch')
        if is_main_branch:
            company = self.cleaned_data.get('company') or (
                self.instance.company if hasattr(self, 'instance') and self.instance else None
            )
            if company:
                qs = Branch.objects.filter(company=company, is_main_branch=True)
                if self.instance and self.instance.pk:
                    qs = qs.exclude(pk=self.instance.pk)
                if qs.exists():
                    raise forms.ValidationError(
                        "Another main branch already exists for this company. "
                        "Only one main branch is allowed."
                    )
        return is_main_branch


class FiscalYearForm(forms.ModelForm):
    start_date_bs = forms.CharField(
        label='Start Date (BS)',
        widget=forms.TextInput(attrs={
            'class': 'nepali-datepicker',
            'placeholder': 'YYYY-MM-DD',
            'autocomplete': 'off',
            'id': 'start_date_bs'
        }),
        required=True,
        help_text='Format: YYYY-MM-DD'
    )

    end_date_bs = forms.CharField(
        label='End Date (BS)',
        widget=forms.TextInput(attrs={
            'class': 'nepali-datepicker',
            'placeholder': 'YYYY-MM-DD',
            'autocomplete': 'off',
            'id': 'end_date_bs'
        }),
        required=True,
        help_text='Format: YYYY-MM-DD'
    )

    class Meta:
        model = FiscalYear
        fields = ['company', 'start_date_bs', 'end_date_bs']

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)

        if self.request and not self.request.user.is_superuser:
            if 'company' in self.fields:
                del self.fields['company']
            self.instance.company = self.request.user.company

    def clean(self):
        cleaned_data = super().clean()
        start_date_bs = cleaned_data.get('start_date_bs')
        end_date_bs = cleaned_data.get('end_date_bs')

        if not start_date_bs:
            self.add_error('start_date_bs', 'Start date (BS) is required')
        if not end_date_bs:
            self.add_error('end_date_bs', 'End date (BS) is required')

        date_format = r'^\d{4}-\d{2}-\d{2}$'  # YYYY-MM-DD
        if start_date_bs and not re.match(date_format, start_date_bs):
            self.add_error('start_date_bs', 'Invalid format. Use YYYY-MM-DD')
        if end_date_bs and not re.match(date_format, end_date_bs):
            self.add_error('end_date_bs', 'Invalid format. Use YYYY-MM-DD')

        return cleaned_data

    def clean_start_date_bs(self):
        start_date_bs = self.cleaned_data.get('start_date_bs')
        try:
            nepali_datetime.datetime.strptime(start_date_bs, '%Y-%m-%d')
        except (ValueError, TypeError):
            raise forms.ValidationError('Invalid BS date format. Use YYYY-MM-DD')
        return start_date_bs

    def clean_end_date_bs(self):
        end_date_bs = self.cleaned_data.get('end_date_bs')
        try:
            nepali_datetime.datetime.strptime(end_date_bs, '%Y-%m-%d')
        except (ValueError, TypeError):
            raise forms.ValidationError('Invalid BS date format. Use YYYY-MM-DD')
        return end_date_bs


