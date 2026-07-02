from django import forms
from django.forms import inlineformset_factory, BaseInlineFormSet
from .models import Vendor, PurchaseOrder, PurchaseOrderItem
from apps.products.models import Product
from apps.bookkeeping.models import LedgerAccount
from ..billing.models import VendorBillItem, VendorBill
from ..payments.models import VendorPayment, BankAccount
from apps.utils.nepali_date import NepaliDateWidget, NepaliDateField, FiscalYearDateMixin
from .services.purchases_services import *


class RequestInlineFormSet(BaseInlineFormSet):
    """Propagates `request` from the formset to each child form."""

    def __init__(self, *args, request=None, **kwargs):
        self.request = request
        super().__init__(*args, **kwargs)

    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        kwargs['request'] = self.request
        return kwargs


class PurchaseOrderForm(FiscalYearDateMixin, forms.ModelForm):
    date = NepaliDateField(widget=NepaliDateWidget(), required=True, label='Date (BS)')

    class Meta:
        model = PurchaseOrder
        fields = ['purchase_order_number', 'status', 'vendor', 'date', 'total_amount']

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)

        if not self.instance.pk:
            self.fields['status'].initial = 'DRAFT'

        if self.request and hasattr(self.request.user, 'company'):
            self.fields['vendor'].queryset = Vendor.active_objects.filter(
                company=self.request.user.company
            )

        self.inject_fiscal_year(self.request)


class PurchaseOrderItemForm(forms.ModelForm):
    expense_account = forms.ModelChoiceField(
        queryset=LedgerAccount.objects.none(),
        required=False,
        label='Expense / Asset Account',
        help_text='Required for Service and Non-Stock lines.',
    )

    class Meta:
        model = PurchaseOrderItem
        fields = ['item_type', 'product', 'description', 'expense_account', 'hscode', 'quantity', 'price']
        widgets = {
            'item_type': forms.Select(attrs={'class': 'item-type-select'}),
            'quantity': forms.NumberInput(attrs={'min': 1, 'class': 'form-control quantity-input'}),
            'price': forms.NumberInput(attrs={'min': 0, 'step': '0.01', 'class': 'form-control price-input'}),
            'description': forms.TextInput(attrs={'class': 'form-control description-input', 'placeholder': 'Service or expense description'}),
        }

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        self.fields['product'].required = False
        self.fields['product'].widget.attrs['class'] = 'product-select'

        # Scope expense_account to the user's company
        company = getattr(getattr(self.request, 'user', None), 'company', None)
        account_qs = LedgerAccount.objects.filter(account_type__in=['ASSET', 'EXPENSE'])
        if company:
            account_qs = account_qs.filter(company=company)
        self.fields['expense_account'].queryset = account_qs.order_by('account_type', 'name')

        # Scope product to the user's company
        if company:
            self.fields['product'].queryset = Product.active_objects.filter(
                company=company
            ).order_by('name')
        else:
            self.fields['product'].queryset = Product.active_objects.none()

    def clean(self):
        cleaned = super().clean()
        item_type = cleaned.get('item_type', 'STOCK')
        product = cleaned.get('product')
        description = cleaned.get('description', '').strip() if cleaned.get('description') else ''

        if item_type == 'STOCK' and not product:
            self.add_error('product', 'Select a product for Stock items.')
        if item_type in ('SERVICE', 'NON_STOCK') and not description:
            self.add_error('description', 'Enter a description for Service / Non-Stock items.')
        return cleaned

    def clean_quantity(self):
        quantity = self.cleaned_data['quantity']
        if quantity <= 0:
            raise forms.ValidationError("Quantity must be positive")
        return quantity

    def clean_price(self):
        price = self.cleaned_data['price']
        if price <= 0:
            raise forms.ValidationError("Price must be positive")
        return price


PurchaseOrderItemFormSet = inlineformset_factory(
    PurchaseOrder,
    PurchaseOrderItem,
    form=PurchaseOrderItemForm,
    formset=RequestInlineFormSet,
    extra=1,
    can_delete=True,
    can_delete_extra=True,
)


class VendorBillForm(FiscalYearDateMixin, forms.ModelForm):
    from apps.utils.constant import PAYMENT_METHOD_CHOICES as _PMC
    bill_date = NepaliDateField(widget=NepaliDateWidget(), required=True,  label='Bill Date (BS)')
    due_date  = NepaliDateField(widget=NepaliDateWidget(), required=False, label='Due Date (BS)')

    collect_payment = forms.BooleanField(
        required=False, label='Record Payment Immediately',
        widget=forms.CheckboxInput(attrs={'id': 'vb-collect-payment-checkbox'}),
    )
    payment_method = forms.ChoiceField(
        choices=[('', 'Select Payment Method')] + list(_PMC),
        required=False, label='Payment Method',
    )
    payment_amount = forms.DecimalField(
        max_digits=10, decimal_places=2, required=False, label='Payment Amount',
    )
    payment_date = NepaliDateField(
        widget=NepaliDateWidget(), required=False, label='Payment Date (BS)',
    )

    class Meta:
        model = VendorBill
        fields = ['vendor', 'purchase_order', 'bill_number', 'bill_date', 'due_date', 'status', 'tax_percent']

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        if self.request and hasattr(self.request.user, 'company'):
            self.fields['vendor'].queryset = Vendor.active_objects.filter(
                company=self.request.user.company
            )
        elif self.request and self.request.user.is_superuser:
            self.fields['vendor'].queryset = Vendor.active_objects.all()
        else:
            self.fields['vendor'].queryset = Vendor.active_objects.none()
        self.inject_fiscal_year(self.request)

class VendorPaymentForm(FiscalYearDateMixin, forms.ModelForm):
    payment_date = NepaliDateField(widget=NepaliDateWidget(), required=True, label='Payment Date (BS)')

    class Meta:
        model = VendorPayment
        fields = ['vendor_bill', 'amount', 'payment_date', 'payment_method', 'bank_account', 'transaction_id']

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        self.fields['bank_account'].required = False
        self.fields['bank_account'].help_text = "Bank account this payment was sent from (Bank Transfer / Cheque)"
        company = getattr(getattr(self.request, 'user', None), 'company', None)
        if company:
            self.fields['bank_account'].queryset = BankAccount.active_objects.filter(company=company, is_active=True)
        else:
            self.fields['bank_account'].queryset = BankAccount.objects.none()
        self.inject_fiscal_year(self.request)

class VendorBillItemForm(forms.ModelForm):
    product = forms.ModelChoiceField(
        queryset=Product.objects.none(),
        label='Product',
        required=False,
    )

    class Meta:
        model = VendorBillItem
        fields = ['product', 'description', 'hscode', 'quantity', 'price']
        widgets = {
            'quantity': forms.NumberInput(attrs={'min': 1}),
            'price': forms.NumberInput(attrs={'min': 0, 'step': '0.01'}),
        }

    def __init__(self, *args, **kwargs):
        company = kwargs.pop('company', None)
        super().__init__(*args, **kwargs)
        if company:
            self.fields['product'].queryset = Product.active_objects.filter(company=company)
        else:
            self.fields['product'].queryset = Product.active_objects.all()


def vendor_bill_item_formset_factory(company=None):
    """Return a formset class with products scoped to the given company."""
    from functools import partial as _partial

    form_cls = type(
        'VendorBillItemFormScoped',
        (VendorBillItemForm,),
        {'__init__': lambda self, *a, **kw: (
            kw.__setitem__('company', company) or None,
            VendorBillItemForm.__init__(self, *a, **kw),
        )[-1]},
    )
    return inlineformset_factory(
        VendorBill, VendorBillItem, form=form_cls, extra=1, can_delete=True
    )


VendorBillItemFormSet = inlineformset_factory(
    VendorBill, VendorBillItem, form=VendorBillItemForm, extra=1, can_delete=True
)