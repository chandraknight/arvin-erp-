from apps.utils.baseModel import BaseModel
from django.db import models


BACKUP_TYPE_CHOICES = [
    ('FULL', 'Full Database (Super Admin)'),
    ('COMPANY', 'Company Data'),
]

STATUS_CHOICES = [
    ('PENDING', 'Pending'),
    ('COMPLETED', 'Completed'),
    ('FAILED', 'Failed'),
]


class BackupRecord(BaseModel):
    backup_type = models.CharField(max_length=10, choices=BACKUP_TYPE_CHOICES)
    company = models.ForeignKey(
        'company.Company',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='backups',
    )
    file_name = models.CharField(max_length=255)
    file_path = models.CharField(max_length=500)
    file_size = models.BigIntegerField(default=0, help_text='Size in bytes')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PENDING')
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.file_name

    @property
    def file_size_display(self):
        size = self.file_size
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"
