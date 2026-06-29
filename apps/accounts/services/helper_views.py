from django.shortcuts import redirect, render

_FEATURES = [
    {'icon': '🧾', 'name': 'Billing & Invoicing', 'desc': 'Tax invoices, credit notes, 3-copy e-billing with IRD CBMS integration.'},
    {'icon': '📦', 'name': 'Inventory', 'desc': 'Products, stock tracking, categories, low-stock alerts.'},
    {'icon': '👥', 'name': 'HR & Payroll', 'desc': 'Employees, attendance, leave, payroll runs, payslips.'},
    {'icon': '🏭', 'name': 'Manufacturing', 'desc': 'BOM, work orders, production runs, machine tracking.'},
    {'icon': '📊', 'name': 'Bookkeeping', 'desc': 'Double-entry accounting, ledger, trial balance, P&L.'},
    {'icon': '🛒', 'name': 'Point of Sale', 'desc': 'Quick counter sales with receipt printing.'},
    {'icon': '🌐', 'name': 'E-Commerce', 'desc': 'Online storefront with COD orders and CMS.'},
    {'icon': '🍽️', 'name': 'Restaurant', 'desc': 'Tables, KOT/BOT, dining orders, printer stations.'},
    {'icon': '✈️', 'name': 'Tours & Ticketing', 'desc': 'Bookings, air files, IATA reconciliation.'},
    {'icon': '📁', 'name': 'Projects', 'desc': 'Cost centres, tasks, milestones, budgets, forecasts.'},
    {'icon': '🔒', 'name': 'RBAC Security', 'desc': 'Role-based access, multi-branch, full audit trail.'},
    {'icon': '📈', 'name': 'Reports', 'desc': 'VAT, P&L, balance sheet, AR aging, and 20+ reports.'},
]


def home_redirect_view(request):
    if request.user.is_authenticated:
        return redirect('accounts:user_dashboard')
    return render(request, 'accounts/landing.html', {'features': _FEATURES})
