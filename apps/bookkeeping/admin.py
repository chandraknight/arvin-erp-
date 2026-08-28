from django.contrib import admin
from .models import (
    LedgerAccount, JournalEntry, JournalEntryLine, LedgerOpeningBalance,
    FixedAsset, TDSRate, TDSDeduction, FixedAssetDepreciationLog,
    PrepaidExpense, PrepaidExpenseAmortizationLog, BalanceConfirmationRequest,
)


@admin.register(LedgerAccount)
class LedgerAccountAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'company')
    list_filter = ('company',)


@admin.register(JournalEntry)
class JournalEntryAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'company')
    list_filter = ('company',)


@admin.register(JournalEntryLine)
class JournalEntryLineAdmin(admin.ModelAdmin):
    list_display = ('__str__',)


@admin.register(LedgerOpeningBalance)
class LedgerOpeningBalanceAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'fiscal_year')
    list_filter = ('fiscal_year',)


@admin.register(FixedAsset)
class FixedAssetAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'company')
    list_filter = ('company',)


@admin.register(TDSRate)
class TDSRateAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'company')
    list_filter = ('company',)


@admin.register(TDSDeduction)
class TDSDeductionAdmin(admin.ModelAdmin):
    list_display = ('__str__',)


@admin.register(FixedAssetDepreciationLog)
class FixedAssetDepreciationLogAdmin(admin.ModelAdmin):
    list_display = ('__str__',)


@admin.register(PrepaidExpense)
class PrepaidExpenseAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'company')
    list_filter = ('company',)


@admin.register(PrepaidExpenseAmortizationLog)
class PrepaidExpenseAmortizationLogAdmin(admin.ModelAdmin):
    list_display = ('__str__',)


@admin.register(BalanceConfirmationRequest)
class BalanceConfirmationRequestAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'company')
    list_filter = ('company',)
