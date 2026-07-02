from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import redirect, get_object_or_404
from django.views.generic import CreateView
from django.contrib import messages
from django.http import HttpResponse
from ..forms import CompanyForm, CompanyAdminUserForm, BranchForm, FiscalYearForm
from ..models import *
from django.urls import reverse_lazy
from ...utils.mixins import AuthMixin


class FiscalYearCreateView(AuthMixin, CreateView):
    model = FiscalYear
    form_class = FiscalYearForm
    template_name = 'company/fiscalyear_form.html'
    success_url = reverse_lazy('company:fiscalyear_list')
    permission_required = ['company.add_fiscalyear']

    def get_template_names(self):
        if self.request.headers.get("HX-Request") == "true" or self.request.GET.get("modal") == "1":
            return ["company/partials/fiscalyear_form_modal.html"]
        return [self.template_name]

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request'] = self.request
        return kwargs

    def form_valid(self, form):
        try:
            start_date_bs = form.cleaned_data.get('start_date_bs')
            end_date_bs = form.cleaned_data.get('end_date_bs')

            if not start_date_bs or not end_date_bs:
                form.add_error(None, "Both start and end BS dates are required")
                return self.form_invalid(form)

            try:
                start_date_ad = nepali_datetime.datetime.strptime(start_date_bs, '%Y-%m-%d').to_datetime_date()
                end_date_ad = nepali_datetime.datetime.strptime(end_date_bs, '%Y-%m-%d').to_datetime_date()
            except Exception as e:
                form.add_error(None, f"Invalid BS date format. Please use YYYY-MM-DD format. Error: {str(e)}")
                return self.form_invalid(form)

            if start_date_ad.year >= end_date_ad.year:
                form.add_error(None, "Start date year must be less than end date year")
                return self.form_invalid(form)

            # Superusers pick company from the form field; regular users get their own company
            if self.request.user.is_superuser:
                company = form.cleaned_data.get('company') or form.instance.company
            else:
                company = self.request.user.company

            if not company:
                form.add_error('company', "Please select a company.")
                return self.form_invalid(form)

            existing_fiscal_years = FiscalYear.objects.filter(
                company=company,
                start_date__lte=end_date_ad,
                end_date__gte=start_date_ad
            )
            if existing_fiscal_years.exists():
                form.add_error(None, "This fiscal year overlaps with an existing one")
                return self.form_invalid(form)

            form.instance.company = company
            form.instance.start_date = start_date_ad
            form.instance.end_date = end_date_ad
            form.instance.start_date_bs = start_date_bs
            form.instance.end_date_bs = end_date_bs

            response = super().form_valid(form)
            messages.success(self.request, "Fiscal Year Added Successfully!")
            if self.request.headers.get("HX-Request") == "true":
                hx = HttpResponse(status=204)
                hx["HX-Redirect"] = str(self.get_success_url())
                return hx
            return response

        except Exception as e:
            form.add_error(None, f"An error occurred: {str(e)}")
            return self.form_invalid(form)

class CompanyCreateAndAssignView(AuthMixin, CreateView):
    """
    Superadmin wizard: create a company and immediately assign an admin user.
    Step 1 (GET)  — show CompanyWithAdminForm
    Step 2 (POST) — create Company + create/assign admin User atomically
    """
    model = Company
    form_class = CompanyForm
    template_name = 'company/company_wizard.html'
    success_url = reverse_lazy('company:company_list')
    permission_required = ['company.add_company']

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_superuser:
            messages.warning(request, "Only superadmins can create companies.")
            return redirect('accounts:user_dashboard')
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Admin user sub-form
        if 'admin_form' not in context:
            context['admin_form'] = CompanyAdminUserForm(prefix='admin')
        return context

    def post(self, request, *args, **kwargs):
        self.object = None  # required by CreateView.get_context_data
        form = CompanyForm(request.POST, request.FILES)
        admin_form = CompanyAdminUserForm(request.POST, prefix='admin')

        if form.is_valid() and admin_form.is_valid():
            return self.forms_valid(form, admin_form)
        else:
            return self.forms_invalid(form, admin_form)

    def forms_valid(self, form, admin_form):
        import logging
        audit = logging.getLogger('audit')
        with transaction.atomic():
            company = form.save()

            # Create or fetch the admin user
            from apps.accounts.models import User
            from django.contrib.auth.models import Group
            email = admin_form.cleaned_data['admin_email']
            password = admin_form.cleaned_data['admin_password']
            first_name = admin_form.cleaned_data['admin_first_name']
            last_name = admin_form.cleaned_data['admin_last_name']

            base_username = email.split('@')[0]
            username = base_username
            suffix = 1
            while User.objects.filter(username=username).exclude(email=email).exists():
                username = f"{base_username}{suffix}"
                suffix += 1

            user, created = User.objects.get_or_create(
                email=email,
                defaults={
                    'username': username,
                    'first_name': first_name,
                    'last_name': last_name,
                    'company': company,
                    'is_active': True,
                }
            )
            if created:
                user.set_password(password)
            else:
                # Existing user — reassign to this company
                user.company = company

            # Assign company admin role
            user.is_company_admin = True
            admin_group, _ = Group.objects.get_or_create(name='Admin')
            user.groups.set([admin_group])
            user.save()

            # Setup default ledger accounts for the new company
            from apps.company.services.company_services import setup_default_ledger_accounts
            setup_default_ledger_accounts(company)

            audit.info(
                'COMPANY_CREATED actor=%s company=%s admin_user=%s',
                self.request.user.email, company.name, email,
            )

        messages.success(
            self.request,
            f"Company '{company.name}' created. Admin user '{email}' assigned."
        )
        return redirect(self.success_url)

    def forms_invalid(self, form, admin_form):
        return self.render_to_response(
            self.get_context_data(form=form, admin_form=admin_form)
        )


class BranchCreateView(AuthMixin, CreateView):
    model = Branch
    form_class = BranchForm
    template_name = 'company/branch_form.html'
    permission_required = ['company.add_branch']

    def dispatch(self, request, *args, **kwargs):
        if getattr(request.user, 'is_company_admin', False) and not request.user.is_superuser:
            raise PermissionDenied('Company admins cannot create branches.')
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        initial = super().get_initial()
        company_id = self.kwargs.get('company_pk')
        if company_id:
            initial['company'] = get_object_or_404(Company, pk=company_id)
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        company_id = self.kwargs.get('company_pk')
        if company_id:
            context['company'] = get_object_or_404(Company, pk=company_id)
        return context

    def get_success_url(self):
        company_id = self.kwargs.get('company_pk')
        if company_id:
            return reverse_lazy('company:company_detail', kwargs={'id': company_id})
        return reverse_lazy('company:branch_list')

    def form_valid(self, form):
        # Ensure that only one main branch exists per company
        if form.cleaned_data.get('is_main_branch'):
            Branch.objects.filter(company=form.instance.company, is_main_branch=True).update(is_main_branch=False)
        messages.success(self.request, "Branch created successfully.")
        return super().form_valid(form)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request'] = self.request
        return kwargs