from enum import Enum


class RoleEnum(Enum):
    Staff = 'Staff'
    Manager = 'Manager'
    Admin = 'Admin'


RUPEE = 'रु'
RUPEE_CODE = 'NPR'

VENDOR_BILL_STATUS_CHOICES = [
    ('UNPAID', 'Unpaid'),
    ('PAID', 'Paid'),
    ('CANCELLED', 'Cancelled'),
]


class StatusChoicesEnum(Enum):
    Issued = 'ISSUED'
    Sent = 'SENT'
    Applied = 'APPLIED'
    Paid = 'PAID'
    Cancelled = 'CANCELLED'
    Submitted = 'SUBMITTED'
    Approved = 'APPROVED'


Bill_STATUS_CHOICES_REMARK = [
    ('SENT', 'Invoice has been created and sent to the customer, but not yet paid.'),
    ('APPLIED', 'Usually means a payment or credit note has been applied to the invoice.'),
    ('PAID', 'Customer has fully paid the invoice'),
    ('CANCELLED', 'The invoice was voided or invalidated, and no payment is expected anymore.'),
]

BILLING_TYPE_CHOICES = [
    ('INVOICE', 'Invoice'),
    ('CREDIT_NOTE', 'Credit Note'),
    ('DEBIT_NOTE', 'Debit Note'),
    ('VENDOR_BILL', 'Vendor Bill'),
]


class BillingTypeEnum(Enum):
    Invoice = 'INVOICE'
    CreditNote = 'CREDIT_NOTE'
    DebitNote = 'DEBIT_NOTE'
    VendorBill = 'VENDOR_BILL'


DEBIT_CREDIT_NOTE_STATUS_CHOICES = [
    ('ISSUED', 'Issued'),
    ('APPLIED', 'Applied'),
    ('CANCELLED', 'Cancelled'),
]

DEBIT_CREDIT_NOTE_REMARK = [
    ('ISSUED', 'The note is complete and officially issued — but not yet applied to any invoice.'),
    ('APPLIED', 'The note has been partially or fully applied to an invoice or vendor bill.'),
    ('CANCELLED', 'The note was voided or invalidated — it no longer affects any financials.'),
]


def is_paid(self):
    return self.status == 'PAID'


PAYMENT_METHOD_CHOICES = [
    ('CASH', 'Cash'),
    ('BANK_TRANSFER', 'Bank Transfer'),
    ('CHEQUE', 'Cheque'),
    ('OTHER', 'Other')
]

PAYMENT_TYPE_CHOICES = [
    ('CUSTOMER', 'Customer Payment'),
    ('VENDOR', 'Vendor Payment'),
    ('EXPENSE', 'Expense Payment'),
    ('SALARY', 'Salary Payment'),
    ('OTHER', 'Other Payment')
]

PURCHASE_STATUS_CHOICES = [
    ('DRAFT', 'Draft'),
    ('SENT', 'Sent'),
    ('RECEIVED', 'Received'),
    ('CANCELLED', 'Cancelled'),
]

PO_APPROVAL_STATUS_CHOICES = [
    ('NOT_REQUIRED', 'Not Required'),
    ('PENDING', 'Pending Approval'),
    ('APPROVED', 'Approved'),
    ('REJECTED', 'Rejected'),
]

PO_ITEM_TYPE_CHOICES = [
    ('STOCK', 'Stock Item'),
    ('SERVICE', 'Service'),
    ('NON_STOCK', 'Non-Stock / Expense'),
]

LEGENDRE_ACCOUNT_TYPES = [
    ('ASSET', 'Asset'),
    ('LIABILITY', 'Liability'),
    ('EQUITY', 'Equity'),
    ('REVENUE', 'Revenue'),
    ('EXPENSE', 'Expense'),
]

JOURNAL_ENTRY_TYPES = [
    ('DEBIT', 'Debit'),
    ('CREDIT', 'Credit'),
]

JOURNAL_SOURCE_TYPES = [
    ('SALES_INVOICE', 'Sales Invoice'),
    ('CREDIT_NOTE', 'Credit Note'),
    ('DEBIT_NOTE', 'Debit Note'),
    ('VENDOR_BILL', 'Vendor Bill'),
    ('PAYMENT', 'Payment'),
    ('EXPENSE', 'Expense'),
    ('PAYROLL', 'Payroll'),
    ('DEPRECIATION', 'Depreciation'),
    ('STOCK_DISPOSAL', 'Stock Disposal'),
    ('OPENING_BALANCE', 'Opening Balance'),
    ('CLOSING_ENTRY', 'Year-End Closing'),
    ('MANUAL_JOURNAL', 'Manual Journal Voucher'),
    ('REVERSAL', 'Reversal'),
    ('BAD_DEBT_WRITEOFF', 'Bad Debt Write-off'),
    ('DOUBTFUL_DEBT_PROVISION', 'Provision for Doubtful Debts'),
    ('ACCRUED_EXPENSE', 'Accrued Expense'),
    ('PREPAID_AMORTIZATION', 'Prepaid Expense Amortization'),
    ('FX_ADJUSTMENT', 'Foreign Exchange Gain/Loss'),
    ('TAX_PROVISION', 'Income Tax Provision'),
    ('CLOSING_STOCK', 'Closing Stock Adjustment'),
    ('OTHER', 'Other'),
]

DEFAULT_ACCOUNTS = [
    {"name": "Accounts Receivable", "account_type": "ASSET",     "code": "1100"},
    {"name": "Sales Revenue",        "account_type": "REVENUE",   "code": "4000"},
    {"name": "Accounts Payable",     "account_type": "LIABILITY", "code": "2100"},
    {"name": "Purchase Expense",     "account_type": "EXPENSE",   "code": "5000"},
    {"name": "Cash",                 "account_type": "ASSET",     "code": "1000"},
    {"name": "Bank",                 "account_type": "ASSET",     "code": "1010"},
    {"name": "Tax Payable",          "account_type": "LIABILITY", "code": "2200"},
    {"name": "Discount Given",       "account_type": "EXPENSE",   "code": "5100"},
    # Input VAT (recoverable) — debit side when receiving a vendor VAT bill
    {"name": "Input VAT",            "account_type": "ASSET",     "code": "1300"},
    # NFRS presentation: revenue and purchases reported net of returns
    {"name": "Sales Returns",        "account_type": "REVENUE",   "code": "4100"},
    {"name": "Purchase Returns",     "account_type": "EXPENSE",   "code": "5200"},
    # Standard operating expense line items — NFRS P&L presentation classifies
    # these separately rather than lumping day-to-day office costs under one
    # generic expense account.
    {"name": "Staff Meal Expense",         "account_type": "EXPENSE", "code": "5300"},
    {"name": "Fuel & Vehicle Expense",     "account_type": "EXPENSE", "code": "5310"},
    {"name": "Communication Expense",      "account_type": "EXPENSE", "code": "5320"},
    {"name": "Office & Administrative Expense", "account_type": "EXPENSE", "code": "5330"},
    {"name": "Rent Expense",               "account_type": "EXPENSE", "code": "5340"},
    {"name": "Utility Expense",            "account_type": "EXPENSE", "code": "5350"},
    {"name": "Repair & Maintenance Expense", "account_type": "EXPENSE", "code": "5360"},
    {"name": "Travel & Conveyance Expense", "account_type": "EXPENSE", "code": "5370"},
    {"name": "Printing & Stationery Expense", "account_type": "EXPENSE", "code": "5380"},
    {"name": "Miscellaneous Expense",      "account_type": "EXPENSE", "code": "5390"},
]
