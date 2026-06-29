"""
Auto-capture CREATE / UPDATE / soft-DELETE on every BaseModel subclass.

We hook into post_save and post_delete.  Because the project uses soft-delete
(is_deleted flag) instead of real deletes, we detect a soft-delete by checking
whether is_deleted changed from False → True on a save.
"""
import json
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.apps import apps

from apps.utils.baseModel import BaseModel
from .middleware import get_current_user, get_current_ip
from .models import ActivityLog

# Fields we never want to diff (noisy / irrelevant)
IGNORED_FIELDS = {
    'updated_at', 'created_at',
    'updated_by_id', 'created_by_id', 'deleted_by_id',
    'password',
}

# Models we skip entirely (too noisy or internal)
SKIP_MODELS = {
    'activitylog',       # don't log the log itself
    'session',
    'logentry',
    'contenttype',
    'permission',
}


def _serialize_value(val):
    """Make a value JSON-safe."""
    if val is None:
        return None
    try:
        json.dumps(val)
        return val
    except (TypeError, ValueError):
        return str(val)


def _get_old_instance(sender, instance):
    """Fetch the pre-save state from the DB."""
    try:
        return sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        return None


# ── pre_save: snapshot old state ──────────────────────────────────────────────

@receiver(pre_save)
def capture_pre_save(sender, instance, **kwargs):
    """Store the old DB state on the instance so post_save can diff it."""
    if not issubclass(sender, BaseModel):
        return
    if sender._meta.model_name in SKIP_MODELS:
        return

    if instance.pk:
        instance._pre_save_state = _get_old_instance(sender, instance)
    else:
        instance._pre_save_state = None


# ── post_save: log CREATE or UPDATE ───────────────────────────────────────────

@receiver(post_save)
def log_post_save(sender, instance, created, **kwargs):
    if not issubclass(sender, BaseModel):
        return
    if sender._meta.model_name in SKIP_MODELS:
        return

    user = get_current_user()
    ip = get_current_ip()

    old = getattr(instance, '_pre_save_state', None)

    # ── Detect soft-delete ────────────────────────────────────────────────────
    if not created and old and not old.is_deleted and instance.is_deleted:
        ActivityLog.log(
            user=user,
            action=ActivityLog.ACTION_DELETE,
            instance=instance,
            ip_address=ip,
        )
        return

    # ── Detect restore (un-delete) ────────────────────────────────────────────
    if not created and old and old.is_deleted and not instance.is_deleted:
        ActivityLog.log(
            user=user,
            action=ActivityLog.ACTION_RESTORE,
            instance=instance,
            ip_address=ip,
        )
        return

    # ── CREATE ────────────────────────────────────────────────────────────────
    if created:
        # Capture key fields for the creation record
        fields = {}
        for field in instance._meta.get_fields():
            if not hasattr(field, 'attname'):
                continue
            fname = field.attname
            if fname in IGNORED_FIELDS:
                continue
            fields[fname] = _serialize_value(getattr(instance, fname, None))

        ActivityLog.log(
            user=user,
            action=ActivityLog.ACTION_CREATE,
            instance=instance,
            changes=fields,
            ip_address=ip,
        )
        return

    # ── UPDATE ────────────────────────────────────────────────────────────────
    if old:
        diff = {}
        for field in instance._meta.get_fields():
            if not hasattr(field, 'attname'):
                continue
            fname = field.attname
            if fname in IGNORED_FIELDS:
                continue
            old_val = _serialize_value(getattr(old, fname, None))
            new_val = _serialize_value(getattr(instance, fname, None))
            if old_val != new_val:
                diff[fname] = {'old': old_val, 'new': new_val}

        if diff:
            ActivityLog.log(
                user=user,
                action=ActivityLog.ACTION_UPDATE,
                instance=instance,
                changes=diff,
                ip_address=ip,
            )
