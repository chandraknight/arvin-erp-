import secrets

from django.db import models

from apps.utils.baseModel import BaseModel


class APIToken(BaseModel):
    """
    Token-based authentication credential for mobile apps and third-party integrations.

    The raw key is only returned once at creation time (TokenCreateResponseSerializer).
    After that, only the token ID, name, scopes, and metadata are accessible.

    Security notes:
    - key is generated with secrets.token_hex(32) — 64 hex chars, 256 bits of entropy.
    - is_active=False immediately revokes the token without deletion (preserves audit trail).
    - expires_at=None means the token never expires.
    - company is nullable to support superuser tokens that span all tenants.
    """

    user = models.ForeignKey(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name='api_tokens',
    )
    company = models.ForeignKey(
        'company.Company',
        on_delete=models.CASCADE,
        related_name='api_tokens',
        null=True,
        blank=True,
        help_text='Null for superuser tokens that are not scoped to a single company.',
    )
    key = models.CharField(
        max_length=64,
        unique=True,
        editable=False,
        help_text='64-char hex token generated with secrets.token_hex(32).',
    )
    name = models.CharField(
        max_length=100,
        help_text='Human-readable label, e.g. "Mobile App", "POS Terminal".',
    )
    scopes = models.JSONField(
        default=list,
        help_text='List of scope strings, e.g. ["invoices:read", "customers:read"].',
    )
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Expiry datetime. Null = never expires.',
    )
    last_used_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Updated on every successful authentication (via update(), not save()).',
    )
    is_active = models.BooleanField(
        default=True,
        help_text='Set to False to revoke the token without deleting it.',
    )

    class Meta:
        verbose_name = 'API Token'
        verbose_name_plural = 'API Tokens'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.name} ({self.user.email})'

    def save(self, *args, **kwargs):
        if not self.key:
            self.key = secrets.token_hex(32)
        super().save(*args, **kwargs)
