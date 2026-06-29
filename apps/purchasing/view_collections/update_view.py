from django.views.generic import UpdateView
from apps.utils.mixins import AuthMixin
from .helper import *


class PurchaseOrderUpdateView(AuthMixin, PurchaseOrderMixin, UpdateView):
    permission_required = ['purchasing.change_purchaseorder']
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