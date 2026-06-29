from django.db import models
from apps.utils.baseModel import BaseModel


class Report(models.Model):
    name = models.CharField(max_length=255)
    report_type = models.CharField(max_length=50, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    class Meta:
        app_label = 'reports'


class UserReportAccess(BaseModel):
    """Company admin grants specific reports to users within the same company."""
    company = models.ForeignKey(
        'company.Company', on_delete=models.CASCADE, related_name='report_access'
    )
    user = models.ForeignKey(
        'accounts.User', on_delete=models.CASCADE, related_name='report_access'
    )
    report_name = models.CharField(max_length=100, help_text='Report slug from REPORT_REGISTRY')
    granted_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, related_name='granted_report_access'
    )

    class Meta:
        app_label = 'reports'
        unique_together = ('company', 'user', 'report_name')

    def __str__(self):
        return f'{self.user} → {self.report_name}'
