from django.contrib import admin
from .models import (
    Invoice, InvoiceItem, BadDebtWriteOff, CreditNote,
    DebitNote, VendorBill, VendorBillItem, CBMSSubmission,
)


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'company', 'fiscal_year')
    list_filter = ('company', 'fiscal_year')


@admin.register(InvoiceItem)
class InvoiceItemAdmin(admin.ModelAdmin):
    list_display = ('__str__',)


@admin.register(BadDebtWriteOff)
class BadDebtWriteOffAdmin(admin.ModelAdmin):
    list_display = ('__str__',)


@admin.register(CreditNote)
class CreditNoteAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'company', 'fiscal_year')
    list_filter = ('company', 'fiscal_year')


@admin.register(DebitNote)
class DebitNoteAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'company', 'fiscal_year')
    list_filter = ('company', 'fiscal_year')


@admin.register(VendorBill)
class VendorBillAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'company')
    list_filter = ('company',)


@admin.register(VendorBillItem)
class VendorBillItemAdmin(admin.ModelAdmin):
    list_display = ('__str__',)


@admin.register(CBMSSubmission)
class CBMSSubmissionAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'company')
    list_filter = ('company',)
