from django.core.exceptions import PermissionDenied
from django.views.generic import DeleteView
from django.shortcuts import *
from django.urls import reverse_lazy
from django.contrib import messages
from ..models import *
from ...utils.decorator import auth_required
from ...utils.mixins import AuthMixin

@auth_required('company.delete_company')
def company_delete_view(request, id):
    if not request.user.is_superuser:
        messages.error(request, "Only superadmins can delete companies.")
        return redirect('company:company_list')

    company = get_object_or_404(Company, pk=id)

    if request.method == 'POST':
        company.name = "deleted_{}".format(company.name)
        company.soft_delete(deleted_by=request.user)
        messages.success(request, "Company deleted successfully.")
        return redirect('company:company_list')

    return redirect('company:company_list')

class BranchDeleteView(AuthMixin, DeleteView):
    model = Branch
    template_name = 'company/branch_confirm_delete.html'
    context_object_name = 'branch'
    permission_required = ['company.delete_branch']
    pk_url_kwarg = 'id'

    def dispatch(self, request, *args, **kwargs):
        if getattr(request.user, 'is_company_admin', False) and not request.user.is_superuser:
            raise PermissionDenied('Company admins cannot delete branches.')
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        return reverse_lazy('company:branch_list')

    def form_valid(self, form):
        messages.success(self.request, "Branch deleted successfully.")
        return super().form_valid(form)
