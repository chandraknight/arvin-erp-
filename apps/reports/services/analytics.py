from django.db.models import Sum, F, Q
from django.db.models.functions import TruncMonth
from apps.billing.models import Invoice, InvoiceItem
from apps.bookkeeping.models import JournalEntry, JournalEntryLine
from apps.company.models import FiscalYear
from apps.payments.models import Payment, VendorPayment
from apps.purchasing.models import Vendor
from datetime import date, timedelta

def get_fiscal_year_trends(company, fiscal_year):
    sales_qs = Invoice.objects.filter(
        company=company,
        created_at__gte=fiscal_year.start_date,
        created_at__lte=fiscal_year.end_date
    ).annotate(month=TruncMonth('created_at')).values('month').annotate(total=Sum('total')).order_by('month')
    expenses_qs = JournalEntryLine.objects.filter(
        account__account_type='EXPENSE',
        journal_entry__company=company,
        journal_entry__date__gte=fiscal_year.start_date,
        journal_entry__date__lte=fiscal_year.end_date
    ).annotate(month=TruncMonth('journal_entry__date')).values('month').annotate(total=Sum('amount')).order_by('month')
    months = set([item['month'] for item in sales_qs] + [item['month'] for item in expenses_qs])
    months = sorted([m for m in months if m is not None])
    labels, sales_data, expenses_data, profit_data = [], [], [], []
    for month in months:
        labels.append(month.strftime('%b %Y'))
        sales = next((item['total'] for item in sales_qs if item['month'] == month), 0)
        expenses = next((item['total'] for item in expenses_qs if item['month'] == month), 0)
        profit = sales - expenses
        sales_data.append(float(sales))
        expenses_data.append(float(expenses))
        profit_data.append(float(profit))
    return labels, sales_data, expenses_data, profit_data

def get_top_customers(company, fiscal_year, n=5):
    qs = Invoice.objects.filter(
        company=company,
        created_at__gte=fiscal_year.start_date,
        created_at__lte=fiscal_year.end_date,
        customer__isnull=False
    ).values('customer__name').annotate(total=Sum('total')).order_by('-total')[:n]
    return [{'name': c['customer__name'], 'total': float(c['total'])} for c in qs]

def get_top_products(company, fiscal_year, n=5):
    qs = InvoiceItem.objects.filter(
        invoice__company=company,
        invoice__created_at__gte=fiscal_year.start_date,
        invoice__created_at__lte=fiscal_year.end_date,
        product__isnull=False
    ).values('product__name').annotate(total=Sum(F('quantity') * F('price'))).order_by('-total')[:n]
    return [{'name': p['product__name'], 'total': float(p['total'])} for p in qs]

def get_yoy_sales(company, fiscal_year):
    prev_fy = FiscalYear.objects.filter(
        company=company,
        end_date__lt=fiscal_year.start_date
    ).order_by('-end_date').first()
    yoy_labels, yoy_sales, yoy_prev_sales = [], [], []
    if prev_fy:
        curr_sales_qs = Invoice.objects.filter(
            company=company,
            created_at__gte=fiscal_year.start_date,
            created_at__lte=fiscal_year.end_date
        ).annotate(month=TruncMonth('created_at')).values('month').annotate(total=Sum('total')).order_by('month')
        prev_sales_qs = Invoice.objects.filter(
            company=company,
            created_at__gte=prev_fy.start_date,
            created_at__lte=prev_fy.end_date
        ).annotate(month=TruncMonth('created_at')).values('month').annotate(total=Sum('total')).order_by('month')
        all_months = set([item['month'] for item in curr_sales_qs] + [item['month'] for item in prev_sales_qs])
        all_months = sorted([m for m in all_months if m is not None])
        for month in all_months:
            yoy_labels.append(month.strftime('%b %Y'))
            curr = next((item['total'] for item in curr_sales_qs if item['month'] == month), 0)
            prev = next((item['total'] for item in prev_sales_qs if item['month'] == month), 0)
            yoy_sales.append(float(curr))
            yoy_prev_sales.append(float(prev))
    return yoy_labels, yoy_sales, yoy_prev_sales

def get_cash_flow(company, fiscal_year):
    # Inflows: Payments received (linked to invoices)
    inflow_qs = Payment.objects.filter(
        company=company,
        date__gte=fiscal_year.start_date,
        date__lte=fiscal_year.end_date,
        amount__gt=0
    ).annotate(month=TruncMonth('date')).values('month').annotate(total=Sum('amount')).order_by('month')
    # Outflows: Vendor payments
    outflow_qs = VendorPayment.objects.filter(
        vendor_bill__vendor__company=company,
        payment_date__gte=fiscal_year.start_date,
        payment_date__lte=fiscal_year.end_date,
        amount__gt=0
    ).annotate(month=TruncMonth('payment_date')).values('month').annotate(total=Sum('amount')).order_by('month')
    months = set([item['month'] for item in inflow_qs] + [item['month'] for item in outflow_qs])
    months = sorted([m for m in months if m is not None])
    labels, inflow_data, outflow_data = [], [], []
    for month in months:
        labels.append(month.strftime('%b %Y'))
        inflow = next((item['total'] for item in inflow_qs if item['month'] == month), 0)
        outflow = next((item['total'] for item in outflow_qs if item['month'] == month), 0)
        inflow_data.append(float(inflow))
        outflow_data.append(float(outflow))
    return labels, inflow_data, outflow_data

def get_ar_aging(company, fiscal_year):
    # Only consider invoices with outstanding balance > 0 and due date in the fiscal year
    today = date.today()
    buckets = {
        'Current': 0,
        '1-30': 0,
        '31-60': 0,
        '61-90': 0,
        '90+': 0,
    }
    invoices = Invoice.objects.filter(
        company=company,
        due_date__gte=fiscal_year.start_date,
        due_date__lte=fiscal_year.end_date,
        outstanding_balance__gt=0
    )
    for inv in invoices:
        if not inv.due_date:
            continue
        days = (today - inv.due_date).days
        if days <= 0:
            buckets['Current'] += float(inv.outstanding_balance)
        elif days <= 30:
            buckets['1-30'] += float(inv.outstanding_balance)
        elif days <= 60:
            buckets['31-60'] += float(inv.outstanding_balance)
        elif days <= 90:
            buckets['61-90'] += float(inv.outstanding_balance)
        else:
            buckets['90+'] += float(inv.outstanding_balance)
    return buckets

def get_vendor_stats(company, fiscal_year, n=5):
    # Top vendors by total paid
    qs = VendorPayment.objects.filter(
        vendor_bill__vendor__company=company,
        payment_date__gte=fiscal_year.start_date,
        payment_date__lte=fiscal_year.end_date
    ).values('vendor_bill__vendor__name').annotate(total=Sum('amount')).order_by('-total')[:n]
    return [{'name': v['vendor_bill__vendor__name'], 'total': float(v['total'])} for v in qs] 