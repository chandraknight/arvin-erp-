from django.views.generic import ListView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.core.exceptions import PermissionDenied
from apps.utils.global_models import *
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages

from apps.utils.mixins import AuthMixin

class BranchListView(AuthMixin, ListView):
    model = Branch
    template_name = 'company/branch_list.html'
    permission_required = ['company.view_branch']
    paginate_by = 10

    def get_paginate_by(self, queryset):
        paginate_by = self.request.GET.get('paginate_by', self.paginate_by)
        try:
            return int(paginate_by)
        except (ValueError, TypeError):
            return self.paginate_by

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser:
            return Branch.active_objects.all()
        elif hasattr(user, 'company'):
            return Branch.active_objects.filter(company=user.company)
        return Branch.active_objects.none()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['paginate_by'] = self.get_paginate_by(self.get_queryset())
        return context

class FiscalYearListView(AuthMixin, ListView):
    model = FiscalYear
    template_name = 'company/fiscalyear_list.html'
    permission_required = ['company.view_fiscalyear']
    paginate_by = 10

    def get_paginate_by(self, queryset):
        paginate_by = self.request.GET.get('paginate_by', self.paginate_by)
        try:
            return int(paginate_by)
        except (ValueError, TypeError):
            return self.paginate_by

    def get_queryset(self):
        queryset = FiscalYear.active_objects.all().order_by('-created_at')
        if not self.request.user.is_superuser:
            user_company = getattr(self.request.user, 'company', None)
            if user_company:
                queryset = queryset.filter(company=user_company)
            else:
                queryset = FiscalYear.objects.none()
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['paginate_by'] = self.get_paginate_by(self.get_queryset())
        return context

@login_required
def select_fiscal_year(request, id):
    fiscal_year_queryset = FiscalYear.active_objects.all() if request.user.is_superuser else FiscalYear.active_objects.filter(
        company=request.user.company)
    fiscal_year = get_object_or_404(fiscal_year_queryset, pk=id)
    request.session['active_fiscal_year_id'] = fiscal_year.id
    messages.success(request, f"Fiscal year {fiscal_year} selected as active.")
    return redirect('company:fiscalyear_list')

class CompanyListView(AuthMixin, ListView):
    model = Company
    template_name = 'company/company_list.html'
    permission_required = ['company.view_company']
    paginate_by = 10

    def get_paginate_by(self, queryset):
        paginate_by = self.request.GET.get('paginate_by', self.paginate_by)
        try:
            return int(paginate_by)
        except (ValueError, TypeError):
            return self.paginate_by

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser:
            return Company.active_objects.all()
        elif hasattr(user, 'company'):
            return Company.active_objects.filter(id=user.company.id)
        return Company.active_objects.none()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['paginate_by'] = self.get_paginate_by(self.get_queryset())
        return context

class CompanyDetailView(AuthMixin, DetailView):
    model = Company
    template_name = 'company/company_detail.html'
    context_object_name = 'company'
    permission_required = 'company.view_company'
    pk_url_kwarg = 'id'

    def get_object(self, queryset=None):
        company = get_object_or_404(Company, id=self.kwargs.get('id'))
        # Non-superusers may only view their own company
        if not self.request.user.is_superuser:
            if not self.request.user.company or self.request.user.company.pk != company.pk:
                raise PermissionDenied('You can only view your own company.')
        return company

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['branches'] = Branch.active_objects.filter(company=self.object)
        return context


class BranchDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = Branch
    template_name = 'company/branch_detail.html'
    context_object_name = 'branch'
    permission_required = 'company.view_branch'
    pk_url_kwarg = 'id'
