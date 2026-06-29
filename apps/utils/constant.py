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
    Draft = 'DRAFT'
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
    ('DRAFT', 'Draft'),
    ('ISSUED', 'Issued'),
    ('APPLIED', 'Applied'),
    ('CANCELLED', 'Cancelled'),
]

DEBIT_CREDIT_NOTE_REMARK = [
    ('DRAFT', 'The note is still being prepared and not yet finalized or sent to the customer/vendor.'),
    ('ISSUED', 'The note is complete and officially issued — but not yet applied to any invoice.'),
    ('APPLIED', 'The note has been partially or fully applied to an invoice or vendor bill.'),
    ('CANCELLED', 'The note was voided or invalidated — it no longer affects any financials.'),
]


def is_draft(self):
    return self.status == 'DRAFT'


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

DEFAULT_ACCOUNTS = [
    {"name": "Accounts Receivable", "account_type": "ASSET", "code": "1100"},
    {"name": "Sales Revenue", "account_type": "REVENUE", "code": "4000"},
    {"name": "Accounts Payable", "account_type": "LIABILITY", "code": "2100"},
    {"name": "Purchase Expense", "account_type": "EXPENSE", "code": "5000"},
    {"name": "Cash", "account_type": "ASSET", "code": "1000"},
    {"name": "Bank", "account_type": "ASSET", "code": "1010"},
    {"name": "Tax Payable", "account_type": "LIABILITY", "code": "2200"},
    {"name": "Discount Given", "account_type": "EXPENSE", "code": "5100"},
]
