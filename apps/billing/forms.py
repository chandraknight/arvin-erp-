from django import forms
from .models import Invoice, InvoiceItem, VendorBill, VendorBillItem, CreditNote, DebitNote
from django.forms import BaseInlineFormSet
from apps.utils.nepali_date import NepaliDateWidget, NepaliDateField, FiscalYearDateMixin
from apps.customers.models import Customer
from apps.company.models import Branch
from apps.bookkeeping.models import LedgerAccount
from ..products.models import CategoryType


class ProductSelectWithStock(forms.Select):
    """Select widget that embeds data-stock on each option for JS consumption."""
    def __init__(self, *args, stock_map=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._stock_map = stock_map or {}

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex=subindex, attrs=attrs)
        pk = str(value.value if hasattr(value, 'value') else value)
        if pk in self._stock_map:
            option['attrs']['data-stock'] = self._stock_map[pk]
        return option


class RequestInlineFormSet(BaseInlineFormSet):
    def __init__(self, *args, request=None, **kwargs):
        self.request = request
        super().__init__(*args, **kwargs)

    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        if hasattr(self, 'request'):
            kwargs['request'] = self.request
        return kwargs


class InvoiceForm(FiscalYearDateMixin, forms.ModelForm):
    # Both date fields use NepaliDateField so BS→AD conversion and
    # fiscal year range validation happen automatically.
    due_date_bs = NepaliDateField(
        widget=NepaliDateWidget(attrs={'id': 'due_date_bs'}),
        required=True,
        label='Date (BS)',
    )
    transaction_date = NepaliDateField(
        widget=NepaliDateWidget(),
        required=True,
        label='Transaction Date (BS)',
    )

    collect_payment = forms.BooleanField(
        required=False,
        label="Collect Payment Immediately",
        widget=forms.CheckboxInput(attrs={'id': 'collect-payment-checkbox'}),
    )

    from apps.utils.constant import PAYMENT_METHOD_CHOICES
    payment_method = forms.ChoiceField(
        choices=[('', 'Select Payment Method')] + list(PAYMENT_METHOD_CHOICES),
        required=False,
        label="Payment Method",
    )

    payment_amount = forms.DecimalField(
        max_digits=10, decimal_places=2, required=False, label="Payment Amount",
    )

    payment_reference = forms.CharField(
        max_length=100, required=False, label="Payment Reference",
    )

    payment_date = NepaliDateField(
        widget=NepaliDateWidget(),
        required=False,
        label="Payment Date (BS)",
    )

    payment_description = forms.CharField(
        required=False, label="Payment Description",
        widget=forms.Textarea(attrs={'rows': 3}),
    )

    class Meta:
        model = Invoice
        fields = [
            'company', 'branch', 'customer', 'transaction_date',
            'subtotal', 'discount_percent', 'discount_amount',
            'tax_percent', 'tax_amount', 'total', 'outstanding_balance', 'due_date_bs',
        ]
        widgets = {
            'invoice_number':      forms.TextInput(attrs={'readonly': 'readonly'}),
            'subtotal':            forms.NumberInput(attrs={'readonly': 'readonly', 'min': '0'}),
            'discount_amount':     forms.NumberInput(attrs={'min': '0', 'step': '0.01'}),
            'discount_percent':    forms.NumberInput(attrs={'min': '0', 'max': '100', 'step': '0.01'}),
            'tax_amount':          forms.NumberInput(attrs={'readonly': 'readonly', 'min': '0'}),
            'tax_percent':         forms.NumberInput(attrs={'min': '0', 'step': '0.01'}),
            'total':               forms.NumberInput(attrs={'readonly': 'readonly', 'min': '0'}),
            'outstanding_balance': forms.NumberInput(attrs={'readonly': 'readonly', 'min': '0'}),
        }
        labels = {
            'discount_amount':     'Discount (₹)',
            'tax_amount':          'Tax (₹)',
            'total':               'Total (₹)',
            'outstanding_balance': 'Outstanding (₹)',
        }

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)

        for field in ['subtotal', 'discount_amount', 'tax_amount', 'total', 'outstanding_balance']:
            self.fields[field].required = False

        self.fields['customer'].required = False
        self.fields['customer'].empty_label = "Walk-in (Cash)"

        if self.request and hasattr(self.request.user, 'company'):
            self.fields['company'].initial = self.request.user.company
            self.fields['customer'].queryset = self.fields['customer'].queryset.filter(
                company=self.request.user.company
            )
            self.fields['branch'].queryset = Branch.objects.filter(
                company=self.request.user.company
            ).order_by('name')
            self.fields['branch'].required = False

            # Tax: only pre-fill if company is VAT registered
            company = self.request.user.company
            if not self.instance.pk:  # create only
                if company and company.vat_registered:
                    self.fields['tax_percent'].initial = company.tax_rate
                else:
                    self.fields['tax_percent'].initial = 0

        # Inject fiscal year — validates all NepaliDateFields against FY range
        self.inject_fiscal_year(self.request)

        # Default both date fields to today (BS) on create only
        if not self.instance.pk:
            from apps.utils.nepali_date import today_bs
            today = today_bs()
            if not self.initial.get('due_date_bs') and not self.data.get('due_date_bs'):
                self.fields['due_date_bs'].initial = today
            if not self.initial.get('transaction_date') and not self.data.get('transaction_date'):
                self.fields['transaction_date'].initial = today

class InvoiceItemForm(forms.ModelForm):
    category_type = forms.ModelChoiceField(
        queryset=CategoryType.active_objects.none(),
        required=False,
        label='Type',
        help_text='Select a category type to filter products.',
    )
    class Meta:
        model = InvoiceItem
        fields = ['item_type', 'product', 'package', 'description', 'hscode', 'quantity', 'price', 'discount_percent', 'discount_amount']
        widgets = {
            # HiddenInput so the field renders as <input type="hidden"> and is
            # valid inside a <tr>. JS manages its value via the type-toggle buttons.
            'item_type': forms.HiddenInput(),
            'price': forms.NumberInput(attrs={'min': '0'}),
            'discount_percent': forms.NumberInput(attrs={'min': '0', 'max': '100', 'step': '0.01'}),
            'discount_amount': forms.NumberInput(attrs={'min': '0', 'step': '0.01'}),
        }

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        category_type = kwargs.pop('category_type', None)
        super().__init__(*args, **kwargs)

        user = getattr(self.request, 'user', None)

        if user and hasattr(user, 'company'):
            company = user.company

            product_qs = self.fields['product'].queryset.filter(company=company).order_by('name')
            package_qs = self.fields['package'].queryset.filter(company=company).order_by('name')

            if category_type:
                product_qs = product_qs.filter(category__type=category_type)
                package_qs = package_qs.filter(items__product__category__type=category_type).distinct()

            self.fields['product'].queryset = product_qs
            self.fields['package'].queryset = package_qs

            # Attach stock data to options so the frontend can display it
            from apps.products.models import ProductStock
            stock_map = {
                str(ps['product_id']): ps['stock']
                for ps in ProductStock.objects.filter(
                    product__company=company, is_deleted=False
                ).values('product_id', 'stock')
            }
            new_widget = ProductSelectWithStock(stock_map=stock_map)
            # Django does not auto-transfer ModelChoiceIterator to a replacement
            # widget, so we must copy the field's choices explicitly.
            new_widget.choices = self.fields['product'].choices
            self.fields['product'].widget = new_widget

        if user and user.is_superuser:
            self.fields['category_type'].queryset = CategoryType.active_objects.all()
        elif user and user.company:
            self.fields['category_type'].queryset = CategoryType.active_objects.filter(company=user.company)
        else:
            self.fields['category_type'].queryset = CategoryType.active_objects.none()

        if category_type:
            self.initial['category_type'] = category_type.id


InvoiceItemFormSet = forms.inlineformset_factory(
    Invoice,
    InvoiceItem,
    form=InvoiceItemForm,
    formset=RequestInlineFormSet,
    extra=1,
    can_delete=True
)


class VendorBillForm(FiscalYearDateMixin, forms.ModelForm):
    from apps.utils.constant import PAYMENT_METHOD_CHOICES
    bill_date = NepaliDateField(widget=NepaliDateWidget(), required=True,  label='Bill Date (BS)')
    due_date  = NepaliDateField(widget=NepaliDateWidget(), required=False, label='Due Date (BS)')

    collect_payment = forms.BooleanField(
        required=False,
        label='Record Payment Immediately',
        widget=forms.CheckboxInput(attrs={'id': 'vb-collect-payment-checkbox'}),
    )
    payment_method = forms.ChoiceField(
        choices=[('', 'Select Payment Method')] + list(PAYMENT_METHOD_CHOICES),
        required=False,
        label='Payment Method',
    )
    payment_amount = forms.DecimalField(
        max_digits=10, decimal_places=2, required=False, label='Payment Amount',
    )
    payment_date = NepaliDateField(
        widget=NepaliDateWidget(), required=False, label='Payment Date (BS)',
    )

    class Meta:
        model = VendorBill
        fields = ['vendor', 'purchase_order', 'bill_number', 'bill_date', 'due_date', 'total_amount']
        widgets = {
            'total_amount': forms.TextInput(attrs={'min': '0'}),
        }

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)

        if self.request and hasattr(self.request.user, 'company'):
            self.fields['vendor'].queryset = self.fields['vendor'].queryset.filter(
                company=self.request.user.company
            )

        self.inject_fiscal_year(self.request)

class VendorBillItemForm(forms.ModelForm):
    class Meta:
        model = VendorBillItem
        fields = ['product', 'description', 'hscode', 'quantity', 'price']
        widgets = {
            'price': forms.TextInput(attrs={'min': '0'}),
            'quantity': forms.TextInput(attrs={'min': '0'}),
        }

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)

        self.fields['quantity'].required = True

        if self.request and hasattr(self.request.user, 'company'):
            company = self.request.user.company
            self.fields['product'].queryset = self.fields['product'].queryset.filter(company=company)

VendorBillItemFormSet = forms.inlineformset_factory(
    VendorBill,
    VendorBillItem,
    form=VendorBillItemForm,
    formset=RequestInlineFormSet,
    extra=1,
    can_delete=True
)


class BaseNoteForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)

        if self.request and hasattr(self.request.user, 'company'):
            company = self.request.user.company
            self.fields['company'].initial = company
            self.fields['company'].disabled = True

            self.fields['customer'].queryset = Customer.objects.filter(company=company).order_by('-created_at')
            self.fields['invoice'].queryset = Invoice.objects.filter(
                company=company,
                invoice_number__isnull=False,
            ).exclude(invoice_number='').order_by('-created_at')

            pass  # status is set by business logic, not the form


class CreditNoteForm(BaseNoteForm):
    class Meta:
        model = CreditNote
        fields = ['company', 'invoice', 'customer', 'amount', 'reason']
        widgets = {
            'reason': forms.Textarea(attrs={'rows': 3}),
        }

    def clean_amount(self):
        amount = self.cleaned_data['amount']
        if amount <= 0:
            raise forms.ValidationError("Amount must be positive.")
        return amount


class DebitNoteForm(BaseNoteForm):
    class Meta:
        model = DebitNote
        fields = ['company', 'invoice', 'customer', 'amount', 'reason']
        widgets = {
            'reason': forms.Textarea(attrs={'rows': 3}),
        }

    def clean_amount(self):
        amount = self.cleaned_data['amount']
        if amount <= 0:
            raise forms.ValidationError("Amount must be positive.")
        return amount