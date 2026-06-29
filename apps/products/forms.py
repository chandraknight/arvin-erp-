from django import forms
from django.forms import inlineformset_factory,BaseInlineFormSet
from .models import Product, Category, ProductStock, Package, PackageItem, CategoryType, ProductImage
from apps.products.models import StockTransaction
from apps.vendors.models import Vendor

class ProductImageForm(forms.ModelForm):
    class Meta:
        model = ProductImage
        fields = ['image', 'is_primary']

ProductImageFormSet = inlineformset_factory(
    Product,
    ProductImage,
    form=ProductImageForm,
    extra=0,
    max_num=20,
    can_delete=True
)

class ItemForm(forms.ModelForm):
    category_type = forms.ModelChoiceField(
        queryset=CategoryType.active_objects.all(),
        required=False,
        label='Type',
        help_text='Select a category type to filter categories.',
    )

    vendor = forms.ModelChoiceField(queryset=Vendor.objects.none(), required=False, label='Preferred Vendor')

    class Meta:
        model = Product
        fields = [
            'name', 'category_type', 'category', 'barcode', 'sku', 'hscode',
            'price', 'compare_at_price', 'cost_price', 'is_service', 'vendor',
        ]
        help_texts = {
            'is_service': 'Check if this product is a service or non-stock item.',
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        category_type = kwargs.pop('category_type', None)
        super().__init__(*args, **kwargs)

        if user:
            if user.is_superuser:
                categories = Category.active_objects.all()
                category_types = CategoryType.objects.all()
                vendors = Vendor.objects.all()
            else:
                categories = Category.active_objects.filter(company=user.company)
                category_types = CategoryType.objects.filter(company=user.company)
                vendors = Vendor.objects.filter(company=user.company)

        self.fields['category'].queryset = categories
        self.fields['category_type'].queryset = category_types
        self.fields['vendor'].queryset = vendors

        if category_type:
            self.fields['category'].queryset = categories.filter(type=category_type)


class StockTransactionForm(forms.ModelForm):
    product = forms.ModelChoiceField(
        queryset=Product.objects.none(),
        disabled=True,
        required=True,
        label="Product"
    )
    class Meta:
        model = StockTransaction
        fields = ['product', 'stock_type', 'transaction_type', 'quantity', 'reason']
        widgets = {
            'reason': forms.Textarea(attrs={'rows': 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        initial_product = self.initial.get('product')

        if isinstance(initial_product, int):
            initial_product = Product.objects.filter(pk=initial_product).first()

        if initial_product:
            self.fields['product'].queryset = Product.objects.filter(pk=initial_product.pk)
            self.initial['product'] = initial_product

class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['type','name', 'parent']

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        if user and not user.is_superuser:
            self.fields['parent'].queryset = Category.active_objects.filter(company=user.company)
            self.fields['type'].queryset = CategoryType.active_objects.filter(company=user.company)
        else:
            self.fields['parent'].queryset = Category.active_objects.all()
            self.fields['type'].queryset = CategoryType.active_objects.all()


class CategoryTypeForm(forms.ModelForm):
    class Meta:
        model = CategoryType
        fields = ['name']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)




class PackageForm(forms.ModelForm):
    class Meta:
        model = Package
        fields = ['name', 'price']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'Package Name'}),
            'price': forms.NumberInput(attrs={'placeholder': 'Total Price'}),
        }


class PackageItemForm(forms.ModelForm):
    product = forms.ModelChoiceField(queryset=Product.active_objects.none(), label='Product', required=True)
    category_type = forms.ModelChoiceField(
        queryset=CategoryType.active_objects.none(),
        required=False,
        label='Type',
        help_text='Select a category type to filter categories.',
    )

    class Meta:
        model = PackageItem
        fields = ['category_type', 'product', 'quantity']
        widgets = {
            'quantity': forms.NumberInput(attrs={'min': 1}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        category_type = kwargs.pop('category_type', None)
        super().__init__(*args, **kwargs)

        product_queryset = Product.active_objects.none()
        category_queryset = Category.active_objects.none()
        category_type_queryset = CategoryType.active_objects.none()

        if user:
            if self.instance and self.instance.pk and self.instance.product:
                product_queryset = Product.active_objects.filter(company=self.instance.product.company)
            elif hasattr(user, 'company') and user.company:
                product_queryset = Product.active_objects.filter(company=user.company)

            if user.is_superuser:
                category_type_queryset = CategoryType.active_objects.all()
            else:
                category_type_queryset = CategoryType.active_objects.filter(company=user.company)

            if category_type:
                self.initial['category_type'] = category_type.id

        self.fields['product'].queryset = product_queryset

        self.fields['category_type'].queryset = category_type_queryset


class BasePackageItemFormSet(BaseInlineFormSet):
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

    def _construct_form(self, i, **kwargs):
        kwargs['user'] = self.user
        return super()._construct_form(i, **kwargs)

    def get_queryset(self):
        # Override to include all items, not just active ones, for update
        if not hasattr(self, '_queryset'):
            if self.instance.pk:
                qs = self.model._default_manager.filter(package=self.instance)
            else:
                qs = self.model._default_manager.none()
            self._queryset = qs
        return self._queryset

    def clean(self):
        super().clean()
        products = set()

        for form in self.forms:
            # Skip forms that are marked for deletion
            if form.cleaned_data.get('DELETE', False):
                continue


PackageItemFormSet = inlineformset_factory(
    Package,
    PackageItem,
    form=PackageItemForm,
    formset=BasePackageItemFormSet,
    extra=0,
    can_delete=True,
    min_num=1,
    max_num=10,
)


