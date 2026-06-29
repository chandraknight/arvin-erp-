from django.shortcuts import redirect
from apps.purchasing.forms import PurchaseOrderForm, PurchaseOrderItemFormSet
from apps.purchasing.models import PurchaseOrder
from django.urls import reverse_lazy
from django.contrib import messages
from django.db import transaction


class PurchaseOrderMixin:
    model = PurchaseOrder
    form_class = PurchaseOrderForm
    template_name = 'purchasing/purchase_order_form.html'
    success_url = reverse_lazy('reports:purchase_order_list_report')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request'] = self.request
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['formset'] = PurchaseOrderItemFormSet(
                self.request.POST,
                instance=self.object,
                request=self.request,
            )
        else:
            context['formset'] = PurchaseOrderItemFormSet(
                instance=self.object,
                request=self.request,
            )
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        formset = context['formset']

        with transaction.atomic():
            if form.is_valid() and formset.is_valid():
                self.object = form.save(commit=False)

                # Set company for new POs
                if not self.object.pk and hasattr(self.request.user, 'company'):
                    self.object.company = self.request.user.company

                self.object.save()
                formset.instance = self.object
                formset.save()

                # Calculate and save total amount
                self.object.total_amount = sum(
                    item.quantity * item.price
                    for item in self.object.items.all()
                )
                self.object.save(update_fields=['total_amount'])

                messages.success(
                    self.request,
                    f"Purchase Order {self.object.purchase_order_number} saved successfully."
                )
                return redirect(self.get_success_url())

        return self.render_to_response(
            self.get_context_data(form=form, formset=formset)
        )