"""
Class-based view mixins for authentication and authorization.

AuthMixin
    Combines LoginRequiredMixin with group-based permission checking.
    Drop-in replacement for LoginRequiredMixin on any CBV.

CompanyRequiredMixin
    Ensures the authenticated user belongs to a company.
    Combine with AuthMixin for full protection.
"""
import logging

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied

logger = logging.getLogger('audit')


class AuthMixin(LoginRequiredMixin):
    """
    Mixin that enforces group-based permission checks on class-based views.

    Set `permission_required` to a string or tuple of permission codenames::

        class MyView(AuthMixin, TemplateView):
            permission_required = ('add_invoice', 'change_invoice')
    """

    permission_required = None

    def get_permission_required(self):
        if isinstance(self.permission_required, str):
            return (self.permission_required,)
        return self.permission_required or ()

    def has_group_permission(self) -> bool:
        if self.request.user.is_superuser or getattr(self.request.user, 'is_company_admin', False):
            return True

        required = {perm.split('.')[-1] for perm in self.get_permission_required()}
        if not required:
            return True

        group_perms = set()
        for group in self.request.user.groups.all():
            group_perms.update(group.permissions.values_list('codename', flat=True))
        group_perms.update(
            self.request.user.user_permissions.values_list('codename', flat=True)
        )

        return required.issubset(group_perms)

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        if not self.has_group_permission():
            missing = (
                {p.split('.')[-1] for p in self.get_permission_required()}
            )
            logger.warning(
                'PERMISSION_DENIED user_id=%s email=%s path=%s missing=%s',
                request.user.pk,
                request.user.email,
                request.path,
                missing,
            )
            raise PermissionDenied(
                'You do not have the required permissions: '
                + ', '.join(sorted(missing))
            )

        return super().dispatch(request, *args, **kwargs)


class CompanyRequiredMixin(LoginRequiredMixin):
    """
    Mixin that blocks access for authenticated users without a company.
    Superusers are exempt.

    Combine with AuthMixin::

        class MyView(AuthMixin, CompanyRequiredMixin, TemplateView):
            permission_required = 'view_invoice'
    """

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        if not request.user.is_superuser and not getattr(request.user, 'company', None):
            logger.warning(
                'COMPANY_REQUIRED_DENIED user_id=%s email=%s path=%s',
                request.user.pk,
                request.user.email,
                request.path,
            )
            raise PermissionDenied(
                'Your account is not associated with a company. '
                'Please contact your administrator.'
            )

        return super().dispatch(request, *args, **kwargs)


class RequestFormMixin:
    """
    Drop this into any CreateView or UpdateView to eliminate three repeated patterns:

      1. get_form_kwargs → injects request into the form automatically.
      2. form_valid on CREATE → stamps company, created_by on form.instance.
      3. form_valid on UPDATE → stamps updated_by on form.instance.

    The mixin detects create vs update by checking form.instance.pk.

    Usage::

        class InvoiceCreateView(AuthMixin, RequestFormMixin, CreateView):
            model = Invoice
            form_class = InvoiceForm
            # No get_form_kwargs, no company/user stamping needed.

    If you need custom form_valid logic, call super() first::

        def form_valid(self, form):
            form.instance.status = 'DRAFT'
            return super().form_valid(form)
    """

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw['request'] = self.request
        return kw

    def form_valid(self, form):
        user = self.request.user
        is_create = not form.instance.pk

        if is_create:
            company = getattr(self.request, 'user_company', None)
            if company and hasattr(form.instance, 'company_id') and not form.instance.company_id:
                form.instance.company = company
            form.instance.created_by = user
        else:
            form.instance.updated_by = user

        return super().form_valid(form)


class CompanyScopedDeleteMixin:
    """
    Drop this into any DeleteView that calls soft_delete.

    Stamps deleted_by automatically::

        class InvoiceDeleteView(AuthMixin, CompanyScopedDeleteMixin, DeleteView):
            model = Invoice
            success_url = reverse_lazy('billing:invoice_list')
    """

    def form_valid(self, form):
        self.object = self.get_object()
        self.object.soft_delete(deleted_by=self.request.user)
        from django.contrib import messages
        from django.shortcuts import redirect
        messages.success(self.request, f"{self.object.__class__.__name__} deleted.")
        return redirect(self.get_success_url())
