from django.contrib import admin
from .models import (
    Report, AccountingPolicyNote, RelatedPartyTransaction, ContingentLiability,
    UserReportAccess,
)


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ('__str__',)


@admin.register(AccountingPolicyNote)
class AccountingPolicyNoteAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'company')
    list_filter = ('company',)


@admin.register(RelatedPartyTransaction)
class RelatedPartyTransactionAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'company', 'fiscal_year')
    list_filter = ('company', 'fiscal_year')


@admin.register(ContingentLiability)
class ContingentLiabilityAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'company', 'fiscal_year')
    list_filter = ('company', 'fiscal_year')


@admin.register(UserReportAccess)
class UserReportAccessAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'company')
    list_filter = ('company',)
