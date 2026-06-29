"""
apps/utils/forms.py
===================
Base form classes that eliminate per-form boilerplate.

Usage
-----
Instead of repeating this in every form:

    class MyForm(forms.ModelForm):
        def __init__(self, *args, request=None, **kwargs):
            super().__init__(*args, **kwargs)
            self.request = request
            company = request.user_company if request else None
            self.fields['vendor'].queryset = Vendor.active_objects.filter(company=company)

Use this:

    class MyForm(CompanyBoundForm):
        class Meta:
            model = MyModel
            fields = [...]

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.scope_qs('vendor', Vendor.active_objects)
            self.scope_qs('customer', Customer.active_objects)
"""

from django import forms


class CompanyBoundForm(forms.ModelForm):
    """
    Base ModelForm that:
      1. Accepts `request` as a keyword argument (no boilerplate in subclasses).
      2. Provides `self.company` shorthand.
      3. Provides `scope_qs(field, manager)` to filter FK fields to the current company.

    Views using RequestFormMixin pass `request` automatically.
    Forms that are instantiated manually should pass request=request.
    """

    def __init__(self, *args, request=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.request = request
        self.company = getattr(request, 'user_company', None) if request else None

    def scope_qs(self, field_name: str, manager):
        """
        Filter a FK/M2M field's queryset to the current company.

        Args:
            field_name: The form field name (must be a ModelChoiceField or similar).
            manager:    A model manager (e.g. Vendor.active_objects) whose .filter(company=...)
                        will be called. If company is None (superuser), returns all active objects.
        """
        if field_name not in self.fields:
            return
        if self.company:
            self.fields[field_name].queryset = manager.filter(company=self.company)
        else:
            self.fields[field_name].queryset = manager.all()
