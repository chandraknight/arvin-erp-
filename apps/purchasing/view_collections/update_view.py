from django.views.generic import UpdateView
from apps.utils.mixins import AuthMixin, ModuleRequiredMixin
from apps.company.fiscal_year_guard import FiscalYearOpenMixin
from .helper import *


class PurchaseOrderUpdateView(AuthMixin, ModuleRequiredMixin, FiscalYearOpenMixin, PurchaseOrderMixin, UpdateView):
    permission_required = ['purchasing.change_purchaseorder']
    module_flag = 'enable_purchasing'
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = f"Edit PO #{self.object.purchase_order_number}"
        context['editing'] = True
        return context

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if 'instance' in kwargs:
            kwargs['initial'] = kwargs.get('initial', {})
            kwargs['initial']['purchase_order_number'] = self.object.purchase_order_number
        return kwargs