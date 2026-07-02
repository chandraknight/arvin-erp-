import logging
import json
from importlib import import_module

from django.contrib.auth import authenticate, login, logout
from django.conf import settings
from .services.all_services import *
from ..utils.global_models import *
from .utils import get_latest_tag
from ..payments.models import Payment

logger = logging.getLogger(__name__)
audit_logger = logging.getLogger('audit')


def login_view(request):
    if request.GET.get('session_expired'):
        messages.warning(request, "Your session has expired. Please login again.")
    if request.user.is_authenticated:
        return redirect('accounts:user_dashboard')
    tag = get_latest_tag()
    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            password = form.cleaned_data['password']
            user = authenticate(request, email=email, password=password)
            if user is None:
                messages.error(request, 'Invalid username or password.')
                return redirect('accounts:login')
            login(request, user)
            request.session.save()  # explicit save before redirect — guards against worker kill
            session_engine = getattr(
                settings,
                "SESSION_ENGINE",
                "django.contrib.sessions.backends.db",
            )
            SessionStore = import_module(session_engine).SessionStore
            encoded_session = request.session.encode(request.session._session)
            try:
                reloaded_session = SessionStore(session_key=request.session.session_key)
                reloaded_user_id = reloaded_session.get('_auth_user_id')
            except Exception:
                audit_logger.error(
                    json.dumps(
                        {
                            "event": "login_session_reload_error",
                            "session_key": request.session.session_key,
                            "session_engine": session_engine,
                            "encoded_session_len": len(encoded_session),
                            "expected_user_id": str(user.pk),
                        },
                        default=str,
                    )
                )
                logger.exception(
                    "login_session_reload_error",
                    extra={
                        "session_key": request.session.session_key,
                        "session_engine": session_engine,
                        "encoded_session_len": len(encoded_session),
                        "expected_user_id": str(user.pk),
                    },
                )
            else:
                if str(reloaded_user_id) != str(user.pk):
                    audit_logger.error(
                        json.dumps(
                            {
                                "event": "login_session_reload_failed",
                                "session_key": request.session.session_key,
                                "session_engine": session_engine,
                                "encoded_session_len": len(encoded_session),
                                "expected_user_id": str(user.pk),
                                "reloaded_user_id": reloaded_user_id,
                            },
                            default=str,
                        )
                    )
                    logger.error(
                        "login_session_reload_failed",
                        extra={
                            "session_key": request.session.session_key,
                            "session_engine": session_engine,
                            "encoded_session_len": len(encoded_session),
                            "expected_user_id": str(user.pk),
                            "reloaded_user_id": reloaded_user_id,
                        },
                    )
            return redirect('accounts:user_dashboard')
    else:
        form = LoginForm()
    return render(request, 'accounts/login.html', {'form': form,'current_tag': tag})


@login_required
def user_dashboard(request):
    from django.utils import timezone
    from django.db.models import Sum, Count, Q
    from apps.products.models import ProductStock
    from apps.purchasing.models import PurchaseOrder
    from apps.vendors.models import Vendor
    from apps.utils.nepali_date import today_bs, ad_date_to_bs_str
    from apps.company.models import FiscalYear

    context = {
        'user': request.user,
        'rupee': RUPEE,
    }

    if request.user.company:
        company = request.user.company
        today = timezone.now().date()

        # Core counts — always shown
        total_customers = Customer.objects.filter(company=company).count()
        total_invoices = Invoice.objects.filter(company=company).count()

        # Sales metrics — always shown
        today_sales = Invoice.objects.filter(
            company=company,
            created_at__date=today
        ).aggregate(total=Sum('total'))['total'] or 0

        # Outstanding receivables — always shown
        total_outstanding = Invoice.objects.filter(
            company=company,
            outstanding_balance__gt=0
        ).aggregate(total=Sum('outstanding_balance'))['total'] or 0

        unpaid_invoices_count = Invoice.objects.filter(
            company=company,
            outstanding_balance__gt=0
        ).count()

        # Active fiscal year
        active_fiscal_year = FiscalYear.objects.filter(
            company=company,
            is_active=True
        ).first()

        # Recent data — always shown
        recent_invoices = Invoice.objects.filter(
            company=company
        ).order_by('-created_at')[:5]

        recent_payments = Payment.objects.filter(
            company=company
        ).order_by('-created_at')[:5]

        context.update({
            'recent_invoices': recent_invoices,
            'recent_payments': recent_payments,
            'total_customers': total_customers,
            'total_invoices': total_invoices,
            'today_sales': today_sales,
            'total_outstanding': total_outstanding,
            'unpaid_invoices_count': unpaid_invoices_count,
            'active_fiscal_year': active_fiscal_year,
            'company': company,
            'today_bs': today_bs(),
        })

        # Inventory stats — only when inventory module is enabled
        if company.enable_inventory:
            total_products = Product.objects.filter(company=company).count()
            low_stock_count = ProductStock.objects.filter(
                product__company=company,
                stock__lte=F('minimum_stock')
            ).count()
            context.update({
                'total_products': total_products,
                'low_stock_count': low_stock_count,
                'show_inventory': True,
            })

        # Purchasing stats — only when purchasing module is enabled
        if company.enable_purchasing:
            total_vendors = Vendor.objects.filter(company=company).count()
            pending_po_count = PurchaseOrder.objects.filter(
                company=company,
                status__in=['DRAFT', 'SENT']
            ).count()
            context.update({
                'total_vendors': total_vendors,
                'pending_po_count': pending_po_count,
                'show_purchasing': True,
            })

        # Orders stats — only when order management is enabled
        if company.enable_order_management:
            from apps.orders.models import SalesOrder
            pending_orders_count = SalesOrder.active_objects.filter(
                company=company,
                status__in=['DRAFT', 'CONFIRMED', 'PROCESSING']
            ).count()
            context.update({
                'pending_orders_count': pending_orders_count,
                'show_orders': True,
            })

        # HR stats — only when HR/Payroll is enabled
        if company.enable_hr_payroll:
            from apps.hrpayroll.models import Employee
            active_employees = Employee.active_objects.filter(
                company=company, is_active=True
            ).count()
            context.update({
                'active_employees': active_employees,
                'show_hr': True,
            })

        # Project stats — only when project tracking is enabled
        if company.enable_project_tracking:
            from apps.projects.models import Project
            active_projects = Project.active_objects.filter(
                company=company, status='ACTIVE'
            ).count()
            context.update({
                'active_projects': active_projects,
                'show_projects': True,
            })

        # Manufacturing stats — only when manufacturing is enabled
        if company.enable_manufacturing:
            from apps.manufacturing.models import WorkOrder
            open_work_orders = WorkOrder.active_objects.filter(
                company=company,
                status__in=['PLANNED', 'IN_PROGRESS']
            ).count()
            context.update({
                'open_work_orders': open_work_orders,
                'show_manufacturing': True,
            })

    return render(request, 'accounts/user_dashboard.html', context)


@login_required
def logout_view(request):
    messages.success(request, "You have been successfully logged out.")
    logout(request)
    return redirect('accounts:login')


def accept_invitation(request, uidb64, token):
    """
    Let a newly created user set their own password via an invitation link.
    Uses the same token mechanism as Django's password reset.
    """
    from django.contrib.auth.tokens import default_token_generator
    from django.utils.http import urlsafe_base64_decode
    from django.utils.encoding import force_str
    from django.contrib.auth import get_user_model
    from django import forms as dj_forms

    UserModel = get_user_model()
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = UserModel.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, UserModel.DoesNotExist):
        user = None

    valid = user is not None and default_token_generator.check_token(user, token)

    if not valid:
        return render(request, 'accounts/invitation_invalid.html')

    if request.method == 'POST':
        from django.contrib.auth.forms import SetPasswordForm
        form = SetPasswordForm(user, request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Password set! You can now log in.")
            return redirect('accounts:login')
    else:
        from django.contrib.auth.forms import SetPasswordForm
        form = SetPasswordForm(user)

    return render(request, 'accounts/invitation.html', {'form': form, 'user_email': user.email})
