from django.utils import timezone
from django.views.generic import CreateView
from apps.utils.mixins import AuthMixin, ModuleRequiredMixin
from apps.company.fiscal_year_guard import FiscalYearOpenMixin
from .helper import *
from ..services.purchases_services import generate_po_number


class PurchaseOrderCreateView(AuthMixin, ModuleRequiredMixin, FiscalYearOpenMixin, PurchaseOrderMixin, CreateView):
    permission_required = ['purchasing.add_purchaseorder']
    module_flag = 'enable_purchasing'
    def get_initial(self):
        company = getattr(self.request.user, 'company', None)
        preview_number = generate_po_number(company.id)[0] if company else ''
        return {
            'date': timezone.now().date(),
            'status': 'SENT',
            'purchase_order_number': preview_number,
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

        # Authoritative number — generated fresh here (not trusted from the
        # get_initial preview) so it stays race-safe and correctly sequenced
        # per fiscal year.
        po_number, sequence, fiscal_year = generate_po_number(form.instance.company.id)
        form.instance.purchase_order_number = po_number
        form.instance.sequence_number = sequence
        form.instance.fiscal_year = fiscal_year

        return super().form_valid(form)