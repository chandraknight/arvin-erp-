from django.utils import timezone
from django.views.generic import CreateView
from apps.utils.mixins import AuthMixin
from .helper import *
from ..services.purchases_services import generate_po_number


class PurchaseOrderCreateView(AuthMixin, PurchaseOrderMixin, CreateView):
    permission_required = ['purchasing.add_purchaseorder']
    def get_initial(self):
        return {
            'date': timezone.now().date(),
            'status': 'DRAFT',
            'purchase_order_number': generate_po_number()
        }

    def form_valid(self, form):
        if hasattr(self.request.user, 'company'):
            form.instance.company = self.request.user.company
        else:
            form.add_error(None, "User is not associated with any company.")
            return self.form_invalid(form)
        # Branch isolation — stamp the user's branch so the PO is owned by it
        user_branch = getattr(self.request, 'user_branch', None)
        if user_branch is not None:
            form.instance.branch = user_branch
        return super().form_valid(form)