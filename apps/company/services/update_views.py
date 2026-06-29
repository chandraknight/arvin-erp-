import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.core.exceptions import PermissionDenied
from django.views.generic import UpdateView
from ..forms import CompanyForm, CompanyBasicInfoForm, BranchForm
from ..models import *
from django.urls import reverse_lazy
from django.shortcuts import redirect, get_object_or_404
from ...utils.htmx import htmx_redirect
from ...utils.mixins import AuthMixin

audit = logging.getLogger('audit')


class CompanyUpdateView(AuthMixin, UpdateView):
    """
    Update a company.

    - Superusers: can edit any company, see all fields (CompanyForm).
    - Company admins: can only edit their own company, see basic info only
      (CompanyBasicInfoForm — no organisation_type or feature flags).
    """
    model = Company
    template_name = 'company/company_update.html'
    context_object_name = 'company'
    permission_required = 'company.change_company'

    def get_form_class(self):
        if self.request.user.is_superuser:
            return CompanyForm
        return CompanyBasicInfoForm

    def get_object(self, queryset=None):
        company = get_object_or_404(Company, id=self.kwargs.get('id'))
        # Non-superusers may only edit their own company
        if not self.request.user.is_superuser:
            if not self.request.user.company or self.request.user.company.pk != company.pk:
                audit.warning(
                    'COMPANY_UPDATE_DENIED user_id=%s email=%s target_company=%s',
                    self.request.user.pk, self.request.user.email, company.pk,
                )
                raise PermissionDenied('You can only edit your own company.')
        return company

    def get_success_url(self):
        return reverse_lazy('company:company_detail', kwargs={'id': self.object.pk})

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request'] = self.request
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if not self.request.user.is_superuser:
            company = self.object
            context['module_flags'] = [
                ('Inventory',         company.enable_inventory),
                ('Purchasing',        company.enable_purchasing),
                ('HR & Payroll',      company.enable_hr_payroll),
                ('Orders & Delivery', company.enable_order_management),
                ('Project Tracking',  company.enable_project_tracking),
                ('Forecasting',       company.enable_forecasting),
                ('Manufacturing',     company.enable_manufacturing),
                ('Branch Accounting', company.enable_branch_accounting),
                ('Restaurant',        company.enable_restaurant),
                ('Point of Sale',     company.enable_pos),
                ('Tours',            company.enable_tours),
                ('E-Commerce Store', company.enable_ecom),
            ]
        return context

    def form_valid(self, form):
        audit.info(
            'COMPANY_UPDATED actor=%s company=%s',
            self.request.user.email, self.object.name,
        )
        messages.success(self.request, 'Company updated successfully.')
        return super().form_valid(form)

class BranchUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = Branch
    form_class = BranchForm
    template_name = 'company/branch_form.html'
    context_object_name = 'branch'
    permission_required = 'company.change_branch'
    pk_url_kwarg = 'id'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['company'] = self.object.company
        return context

    def get_success_url(self):
        return reverse_lazy('company:company_detail', kwargs={'id': self.object.company.pk})

    def form_valid(self, form):
        if form.cleaned_data.get('is_main_branch'):
            Branch.objects.filter(company=form.instance.company, is_main_branch=True).exclude(pk=form.instance.pk).update(is_main_branch=False)
        messages.success(self.request, "Branch updated successfully.")
        return super().form_valid(form)
