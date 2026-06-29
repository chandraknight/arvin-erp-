"""
Central registry of all reports.

Each entry maps a report slug to its display metadata and the Company
feature-flag that must be True for the report to appear.  A None flag means
the report is always visible (core financial/bookkeeping).

module_flag values must match a BooleanField name on apps.company.models.Company.
"""

REPORT_REGISTRY = {
    # ── Financial Statements (always visible) ──────────────────────────────
    'balance_sheet_report': {
        'label': 'Balance Sheet',
        'description': 'Assets, Liabilities & Equity at a point in time',
        'url_name': 'reports:balance_sheet_report',
        'section': 'Financial Statements',
        'icon': 'fas fa-balance-scale',
        'color': 'blue',
        'module_flag': None,
    },
    'profit_and_loss_report': {
        'label': 'Profit & Loss',
        'description': 'Revenue, expenses, and net income over a period',
        'url_name': 'reports:profit_and_loss_report',
        'section': 'Financial Statements',
        'icon': 'fas fa-chart-line',
        'color': 'green',
        'module_flag': None,
    },
    'trial_balance_report': {
        'label': 'Trial Balance',
        'description': 'Summary of all ledger account balances',
        'url_name': 'reports:trial_balance_report',
        'section': 'Financial Statements',
        'icon': 'fas fa-list-alt',
        'color': 'indigo',
        'module_flag': None,
    },
    'cash_flow_report': {
        'label': 'Cash Flow',
        'description': 'Cash inflows and outflows over a period',
        'url_name': 'reports:cash_flow_report',
        'section': 'Financial Statements',
        'icon': 'fas fa-water',
        'color': 'purple',
        'module_flag': None,
    },
    'ratio_analysis_report': {
        'label': 'Ratio Analysis',
        'description': 'Liquidity, profitability, and solvency ratios',
        'url_name': 'reports:ratio_analysis_report',
        'section': 'Financial Statements',
        'icon': 'fas fa-percentage',
        'color': 'teal',
        'module_flag': None,
    },
    'changes_in_equity_report': {
        'label': 'Changes in Equity',
        'description': 'NFRS — statement of changes in equity',
        'url_name': 'reports:changes_in_equity_report',
        'section': 'Financial Statements',
        'icon': 'fas fa-chart-area',
        'color': 'violet',
        'module_flag': None,
    },
    'fixed_asset_register_report': {
        'label': 'Fixed Asset Register',
        'description': 'NFRS 13 — fixed asset depreciation schedule',
        'url_name': 'reports:fixed_asset_register_report',
        'section': 'Financial Statements',
        'icon': 'fas fa-building',
        'color': 'gray',
        'module_flag': None,
    },

    # ── Sales Reports (always visible) ────────────────────────────────────
    'detailed_sales_report': {
        'label': 'Detailed Sales',
        'description': 'All invoices with date range filtering',
        'url_name': 'reports:detailed_sales_report',
        'section': 'Sales Reports',
        'icon': 'fas fa-file-invoice-dollar',
        'color': 'green',
        'module_flag': None,
    },
    'sales_by_customer_report': {
        'label': 'Sales by Customer',
        'description': 'Revenue breakdown per customer',
        'url_name': 'reports:sales_by_customer_report',
        'section': 'Sales Reports',
        'icon': 'fas fa-user-friends',
        'color': 'teal',
        'module_flag': None,
    },
    'sales_by_category_report': {
        'label': 'Sales by Category',
        'description': 'Revenue grouped by product category',
        'url_name': 'reports:sales_by_category_report',
        'section': 'Sales Reports',
        'icon': 'fas fa-tags',
        'color': 'yellow',
        'module_flag': None,
    },
    'revenue_by_time_report': {
        'label': 'Revenue by Time',
        'description': 'Monthly and yearly revenue trends',
        'url_name': 'reports:revenue_by_time_report',
        'section': 'Sales Reports',
        'icon': 'fas fa-calendar-alt',
        'color': 'orange',
        'module_flag': None,
    },
    'sales_by_user_report': {
        'label': 'Sales by User',
        'description': 'Sales performance per staff member',
        'url_name': 'reports:sales_by_user_report',
        'section': 'Sales Reports',
        'icon': 'fas fa-user',
        'color': 'cyan',
        'module_flag': None,
    },
    'referral_report': {
        'label': 'Referrals',
        'description': 'Sales from referral sources',
        'url_name': 'reports:referral_report',
        'section': 'Sales Reports',
        'icon': 'fas fa-share-alt',
        'color': 'pink',
        'module_flag': None,
    },
    'sales_by_reference_report': {
        'label': 'Sales by Reference',
        'description': 'Invoices grouped by customer PO#, contract#, or cheque#',
        'url_name': 'reports:sales_by_reference_report',
        'section': 'Sales Reports',
        'icon': 'fas fa-tag',
        'color': 'violet',
        'module_flag': None,
    },

    # ── Inventory Reports (require enable_inventory) ───────────────────────
    'product_sales_report': {
        'label': 'Product Sales',
        'description': 'Quantity and revenue per product',
        'url_name': 'reports:product_sales_report',
        'section': 'Inventory & Products',
        'icon': 'fas fa-box',
        'color': 'lime',
        'module_flag': 'enable_inventory',
    },
    'service_sales_report': {
        'label': 'Service Sales',
        'description': 'Revenue from service line items',
        'url_name': 'reports:service_sales_report',
        'section': 'Sales Reports',
        'icon': 'fas fa-concierge-bell',
        'color': 'emerald',
        'module_flag': None,
    },
    'product_performance_report': {
        'label': 'Product Performance',
        'description': 'Top-selling products by revenue',
        'url_name': 'reports:product_performance_report',
        'section': 'Inventory & Products',
        'icon': 'fas fa-chart-bar',
        'color': 'rose',
        'module_flag': 'enable_inventory',
    },
    'inventory_report': {
        'label': 'Inventory Status',
        'description': 'Current stock levels and low-stock alerts',
        'url_name': 'reports:inventory_report',
        'section': 'Inventory & Products',
        'icon': 'fas fa-warehouse',
        'color': 'purple',
        'module_flag': 'enable_inventory',
    },
    'vendor_wise_inventory_report': {
        'label': 'Vendor-wise Inventory',
        'description': 'Stock and value grouped by preferred vendor',
        'url_name': 'reports:vendor_wise_inventory_report',
        'section': 'Inventory & Products',
        'icon': 'fas fa-truck-loading',
        'color': 'indigo',
        'module_flag': 'enable_inventory',
    },
    'purchase_price_history_report': {
        'label': 'Purchase Price History',
        'description': 'Cost price changes per product across vendor bills',
        'url_name': 'reports:purchase_price_history_report',
        'section': 'Inventory & Products',
        'icon': 'fas fa-history',
        'color': 'orange',
        'module_flag': 'enable_inventory',
    },
    'stock_movement_report': {
        'label': 'Stock Movement',
        'description': 'Stock additions, removals, and adjustments',
        'url_name': 'reports:stock_movement_report',
        'section': 'Inventory & Products',
        'icon': 'fas fa-exchange-alt',
        'color': 'fuchsia',
        'module_flag': 'enable_inventory',
    },
    'cogs_report': {
        'label': 'COGS',
        'description': 'Cost of goods sold per product',
        'url_name': 'reports:cogs_report',
        'section': 'Inventory & Products',
        'icon': 'fas fa-calculator',
        'color': 'pink',
        'module_flag': 'enable_inventory',
    },
    'profitability_report': {
        'label': 'Profitability',
        'description': 'Gross profit: sales minus COGS',
        'url_name': 'reports:profitability_report',
        'section': 'Inventory & Products',
        'icon': 'fas fa-percentage',
        'color': 'sky',
        'module_flag': 'enable_inventory',
    },

    # ── Receivables & Payments (always visible) ───────────────────────────
    'outstanding_invoices_report': {
        'label': 'Outstanding Invoices',
        'description': 'Unpaid invoices with balances due',
        'url_name': 'reports:outstanding_invoices_report',
        'section': 'Receivables & Payments',
        'icon': 'fas fa-file-invoice',
        'color': 'red',
        'module_flag': None,
    },
    'ar_aging_report': {
        'label': 'A/R Aging',
        'description': 'Receivables by age: 30, 60, 90+ days',
        'url_name': 'reports:ar_aging_report',
        'section': 'Receivables & Payments',
        'icon': 'fas fa-hourglass-half',
        'color': 'amber',
        'module_flag': None,
    },
    'payment_history_report': {
        'label': 'Payment History',
        'description': 'All customer payments received',
        'url_name': 'reports:payment_history_report',
        'section': 'Receivables & Payments',
        'icon': 'fas fa-money-check-alt',
        'color': 'blue',
        'module_flag': None,
    },
    'debit_credit_note_report': {
        'label': 'Debit / Credit Notes',
        'description': 'All issued debit and credit notes',
        'url_name': 'reports:debit_credit_note_report',
        'section': 'Receivables & Payments',
        'icon': 'fas fa-receipt',
        'color': 'violet',
        'module_flag': None,
    },
    'ap_aging_report': {
        'label': 'A/P Aging',
        'description': 'Payables by age: 30, 60, 90+ days',
        'url_name': 'reports:ap_aging_report',
        'section': 'Receivables & Payments',
        'icon': 'fas fa-hourglass',
        'color': 'orange',
        'module_flag': 'enable_purchasing',
    },
    'cash_position_report': {
        'label': 'Cash Position',
        'description': 'Real-time cash and bank balances',
        'url_name': 'reports:cash_position_report',
        'section': 'Receivables & Payments',
        'icon': 'fas fa-coins',
        'color': 'yellow',
        'module_flag': None,
    },

    # ── Purchasing & Vendor (require enable_purchasing) ───────────────────
    # Note: vendor_bill_list, vendor_payment_list, and purchase_order_list
    # live in the purchasing app (purchasing:vendor_bill_list etc.) — not here.

    # ── Customers ─────────────────────────────────────────────────────────
    'customer_acquisition_report': {
        'label': 'Customer Acquisition',
        'description': 'New customers over time',
        'url_name': 'reports:customer_acquisition_report',
        'section': 'Customers',
        'icon': 'fas fa-user-plus',
        'color': 'teal',
        'module_flag': None,
    },

    # ── Tax / VAT ─────────────────────────────────────────────────────────
    'tax_report': {
        'label': 'Tax / VAT Report',
        'description': 'Output vs input tax summary for a date range',
        'url_name': 'reports:tax_report',
        'section': 'Tax & VAT',
        'icon': 'fas fa-receipt',
        'color': 'amber',
        'module_flag': 'vat_registered',
    },
    'vat_period_report': {
        'label': 'VAT Filing Periods',
        'description': 'Monthly, 4-monthly, or bi-yearly VAT payable',
        'url_name': 'reports:vat_period_report',
        'section': 'Tax & VAT',
        'icon': 'fas fa-calendar-check',
        'color': 'red',
        'module_flag': 'vat_registered',
    },

    # ── Bookkeeping ───────────────────────────────────────────────────────
    'ledger_account_list_report': {
        'label': 'Ledger Accounts',
        'description': 'Chart of accounts with balances',
        'url_name': 'reports:ledger_account_list_report',
        'section': 'Bookkeeping',
        'icon': 'fas fa-book',
        'color': 'indigo',
        'module_flag': None,
    },
    'journal_entry_list_report': {
        'label': 'Journal Entries',
        'description': 'All double-entry journal transactions',
        'url_name': 'reports:journal_entry_list_report',
        'section': 'Bookkeeping',
        'icon': 'fas fa-book-open',
        'color': 'blue',
        'module_flag': None,
    },
    'payment_list_report': {
        'label': 'Payment List',
        'description': 'All payment transactions',
        'url_name': 'reports:payment_list_report',
        'section': 'Bookkeeping',
        'icon': 'fas fa-list',
        'color': 'cyan',
        'module_flag': None,
    },
    'fiscal_year_dashboard': {
        'label': 'Fiscal Year Dashboard',
        'description': 'Analytics and trends for the fiscal year',
        'url_name': 'reports:fiscal_year_dashboard',
        'section': 'Bookkeeping',
        'icon': 'fas fa-calendar-check',
        'color': 'green',
        'module_flag': None,
    },

    # ── HR & Payroll (require enable_hr_payroll) ──────────────────────────
    'payroll_summary_report': {
        'label': 'Payroll Summary',
        'description': 'Payroll costs by employee and period',
        'url_name': 'reports:payroll_summary_report',
        'section': 'HR & Payroll',
        'icon': 'fas fa-users',
        'color': 'indigo',
        'module_flag': 'enable_hr_payroll',
    },

    # ── Manufacturing (require enable_manufacturing) ──────────────────────
    'manufacturing_work_orders': {
        'label': 'Work Orders',
        'description': 'All production work orders and their status',
        'url_name': 'manufacturing:work_order_list',
        'section': 'Manufacturing',
        'icon': 'fas fa-industry',
        'color': 'slate',
        'module_flag': 'enable_manufacturing',
    },
    'manufacturing_production_runs': {
        'label': 'Production Runs',
        'description': 'Completed production batch runs',
        'url_name': 'manufacturing:production_run_list',
        'section': 'Manufacturing',
        'icon': 'fas fa-cogs',
        'color': 'gray',
        'module_flag': 'enable_manufacturing',
    },

    # ── Tours & Travel (require enable_tours) ─────────────────────────────
    'tours_bookings': {
        'label': 'Tour Bookings',
        'description': 'All tour package bookings',
        'url_name': 'tours:booking_list',
        'section': 'Tours & Travel',
        'icon': 'fas fa-map-marked-alt',
        'color': 'green',
        'module_flag': 'enable_tours',
    },
    'tours_tickets': {
        'label': 'Air Tickets',
        'description': 'Issued air tickets and IATA records',
        'url_name': 'tours:ticket_list',
        'section': 'Tours & Travel',
        'icon': 'fas fa-plane',
        'color': 'sky',
        'module_flag': 'enable_tours',
    },
    'tours_enquiries': {
        'label': 'Tour Enquiries',
        'description': 'Pending and converted tour enquiries',
        'url_name': 'tours:enquiry_list',
        'section': 'Tours & Travel',
        'icon': 'fas fa-question-circle',
        'color': 'yellow',
        'module_flag': 'enable_tours',
    },

    # ── Projects (require enable_project_tracking) ────────────────────────
    'project_list': {
        'label': 'Projects',
        'description': 'All projects with budget and status',
        'url_name': 'projects:project_list',
        'section': 'Projects',
        'icon': 'fas fa-project-diagram',
        'color': 'violet',
        'module_flag': 'enable_project_tracking',
    },
    'project_budget_report': {
        'label': 'Budget vs Actual',
        'description': 'Project budgets vs actual spend',
        'url_name': 'projects:budget_list',
        'section': 'Projects',
        'icon': 'fas fa-chart-pie',
        'color': 'indigo',
        'module_flag': 'enable_project_tracking',
    },
}

# Ordered section list for dashboard display
SECTION_ORDER = [
    'Financial Statements',
    'Sales Reports',
    'Receivables & Payments',
    'Inventory & Products',
    'Purchasing & Vendors',
    'Customers',
    'Tax & VAT',
    'Bookkeeping',
    'HR & Payroll',
    'Manufacturing',
    'Tours & Travel',
    'Projects',
]

SECTION_ICONS = {
    'Financial Statements': ('fas fa-balance-scale', 'blue'),
    'Sales Reports': ('fas fa-chart-bar', 'green'),
    'Receivables & Payments': ('fas fa-money-bill-wave', 'yellow'),
    'Inventory & Products': ('fas fa-boxes', 'purple'),
    'Purchasing & Vendors': ('fas fa-truck', 'orange'),
    'Customers': ('fas fa-users', 'teal'),
    'Tax & VAT': ('fas fa-receipt', 'amber'),
    'Bookkeeping': ('fas fa-book', 'indigo'),
    'HR & Payroll': ('fas fa-user-tie', 'indigo'),
    'Manufacturing': ('fas fa-industry', 'slate'),
    'Tours & Travel': ('fas fa-plane', 'sky'),
    'Projects': ('fas fa-project-diagram', 'violet'),
}


def get_enabled_reports(company):
    """Return set of report slugs accessible based on company feature flags."""
    enabled = set()
    for slug, meta in REPORT_REGISTRY.items():
        flag = meta['module_flag']
        if flag is None or (company and getattr(company, flag, False)):
            enabled.add(slug)
    return enabled


def get_user_visible_reports(user, company):
    """
    Return set of report slugs this user can see on the dashboard.

    - superuser / company_admin → all enabled for company
    - regular staff → intersection of enabled + what admin granted
    """
    from apps.reports.models import UserReportAccess
    company_enabled = get_enabled_reports(company)
    if not company or user.is_superuser or user.is_company_admin:
        return company_enabled
    granted = set(
        UserReportAccess.objects.filter(
            company=company, user=user, is_deleted=False
        ).values_list('report_name', flat=True)
    )
    return company_enabled & granted


def get_dashboard_sections(visible_slugs):
    """
    Return ordered list of (section_name, icon, color, [report_meta, ...])
    for all sections that have at least one visible report.
    """
    sections = {}
    for slug, meta in REPORT_REGISTRY.items():
        if slug not in visible_slugs:
            continue
        sec = meta['section']
        if sec not in sections:
            sections[sec] = []
        sections[sec].append({'slug': slug, **meta})

    result = []
    for sec in SECTION_ORDER:
        if sec in sections:
            icon, color = SECTION_ICONS.get(sec, ('fas fa-file', 'gray'))
            result.append({
                'name': sec,
                'icon': icon,
                'color': color,
                'reports': sections[sec],
            })
    return result
