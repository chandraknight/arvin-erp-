import uuid
from django.db import models
from django.conf import settings


class ActivityLog(models.Model):
    """
    Immutable audit trail for every create / update / soft-delete action
    performed on any BaseModel subclass across the ERP.

    Records are NEVER deleted — they are the source of truth for "who did what".
    """

    ACTION_CREATE  = 'CREATE'
    ACTION_UPDATE  = 'UPDATE'
    ACTION_DELETE  = 'DELETE'   # soft-delete
    ACTION_LOGIN   = 'LOGIN'
    ACTION_LOGOUT  = 'LOGOUT'
    ACTION_RESTORE = 'RESTORE'
    ACTION_REVERSE = 'REVERSE'  # accounting reversal journal

    ACTION_CHOICES = [
        (ACTION_CREATE,  'Created'),
        (ACTION_UPDATE,  'Updated'),
        (ACTION_DELETE,  'Deleted'),
        (ACTION_LOGIN,   'Logged In'),
        (ACTION_LOGOUT,  'Logged Out'),
        (ACTION_RESTORE, 'Restored'),
        (ACTION_REVERSE, 'Reversed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Who
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='activity_logs',
    )
    user_email = models.EmailField(blank=True)          # snapshot in case user is deleted
    company_name = models.CharField(max_length=255, blank=True)

    # What
    action = models.CharField(max_length=10, choices=ACTION_CHOICES)
    app_label = models.CharField(max_length=100, blank=True)
    model_name = models.CharField(max_length=100, blank=True)
    object_id = models.CharField(max_length=255, blank=True)
    object_repr = models.CharField(max_length=500, blank=True,
                                   help_text='String representation of the object at the time of action')

    # Change detail
    changes = models.JSONField(
        null=True, blank=True,
        help_text='{"field": {"old": ..., "new": ...}} for UPDATE; full data for CREATE'
    )
    extra = models.JSONField(null=True, blank=True,
                             help_text='Any extra context (e.g. IP, user-agent)')

    # When / Where
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['model_name', 'object_id']),
            models.Index(fields=['user', 'timestamp']),
            models.Index(fields=['action', 'timestamp']),
        ]
        verbose_name = 'Activity Log'
        verbose_name_plural = 'Activity Logs'

    def __str__(self):
        return f"[{self.timestamp:%Y-%m-%d %H:%M}] {self.user_email} {self.action} {self.model_name} {self.object_id}"

    @classmethod
    def log(cls, *, user=None, action, instance=None, model_name='', object_id='',
            object_repr='', changes=None, ip_address=None, extra=None):
        """
        Convenience factory.  Call from signals or views.
        """
        user_email = ''
        company_name = ''

        if user and not user.is_anonymous:
            user_email = getattr(user, 'email', '') or ''
            company_name = getattr(getattr(user, 'company', None), 'name', '') or ''

        if instance is not None:
            from django.contrib.contenttypes.models import ContentType
            ct = ContentType.objects.get_for_model(instance.__class__)
            model_name = model_name or ct.model
            object_id = object_id or str(instance.pk)
            object_repr = object_repr or str(instance)[:500]

        cls.objects.create(
            user=user if (user and not user.is_anonymous) else None,
            user_email=user_email,
            company_name=company_name,
            action=action,
            app_label=instance._meta.app_label if instance else '',
            model_name=model_name,
            object_id=object_id,
            object_repr=object_repr,
            changes=changes,
            ip_address=ip_address,
            extra=extra,
        )
