from django.contrib import admin
from .models import (
    BankAccount, BankReconciliation, VendorPayment, Payment,
    Expense,
)


@admin.register(BankAccount)
class BankAccountAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'company')
    list_filter = ('company',)


@admin.register(BankReconciliation)
class BankReconciliationAdmin(admin.ModelAdmin):
    list_display = ('__str__',)


@admin.register(VendorPayment)
class VendorPaymentAdmin(admin.ModelAdmin):
    list_display = ('__str__',)


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'company', 'fiscal_year')
    list_filter = ('company', 'fiscal_year')


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'company')
    list_filter = ('company',)
