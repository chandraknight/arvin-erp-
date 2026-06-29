import mimetypes
import os

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import BackupRecord
from .services import (
    create_company_backup,
    create_full_backup,
    delete_backup,
    restore_company_backup,
    restore_full_backup,
)


def _can_access_backup(user, record):
    if user.is_superuser:
        return True
    if user.is_company_admin and record.backup_type == 'COMPANY':
        return record.company_id == user.company_id
    return False


@login_required
def backup_list(request):
    if not (request.user.is_superuser or request.user.is_company_admin):
        raise PermissionDenied

    if request.user.is_superuser:
        records = BackupRecord.objects.all()
    else:
        records = BackupRecord.objects.filter(
            backup_type='COMPANY', company=request.user.company
        )
    return render(request, 'backup/backup_list.html', {'records': records})


@login_required
@require_POST
def backup_create(request):
    if not (request.user.is_superuser or request.user.is_company_admin):
        raise PermissionDenied

    try:
        if request.user.is_superuser and request.POST.get('type') == 'FULL':
            create_full_backup(request.user)
            messages.success(request, "Full database backup completed successfully.")
        else:
            # Company backup: works for both company_admin (their company)
            # and superuser who has a company assigned.
            company = request.user.company
            if not company:
                messages.error(request, "Your account has no company assigned. Ask a super-admin to set one.")
                return redirect('backup:backup_list')
            create_company_backup(company, request.user)
            messages.success(request, f"Backup for {company.name} completed successfully.")
    except Exception as exc:
        messages.error(request, f"Backup failed: {exc}")

    return redirect('backup:backup_list')


@login_required
def backup_download(request, pk):
    record = get_object_or_404(BackupRecord, pk=pk)
    if not _can_access_backup(request.user, record):
        raise PermissionDenied
    if not record.file_path or not os.path.exists(record.file_path):
        raise Http404("Backup file not found on disk.")

    content_type, _ = mimetypes.guess_type(record.file_path)
    response = FileResponse(
        open(record.file_path, 'rb'),
        content_type=content_type or 'application/octet-stream',
        as_attachment=True,
        filename=record.file_name,
    )
    return response


@login_required
def backup_confirm_restore(request, pk):
    record = get_object_or_404(BackupRecord, pk=pk)
    if not _can_access_backup(request.user, record):
        raise PermissionDenied
    return render(request, 'backup/backup_confirm_restore.html', {'record': record})


@login_required
@require_POST
def backup_restore(request, pk):
    record = get_object_or_404(BackupRecord, pk=pk)
    if not _can_access_backup(request.user, record):
        raise PermissionDenied

    try:
        if record.backup_type == 'FULL':
            restore_full_backup(record, request.user)
            messages.success(request, "Full database restored successfully.")
        else:
            restore_company_backup(record, request.user)
            messages.success(request, f"Company data restored from {record.file_name}.")
    except Exception as exc:
        messages.error(request, f"Restore failed: {exc}")

    return redirect('backup:backup_list')


@login_required
@require_POST
def backup_delete(request, pk):
    record = get_object_or_404(BackupRecord, pk=pk)
    if not _can_access_backup(request.user, record):
        raise PermissionDenied

    name = record.file_name
    delete_backup(record)
    messages.success(request, f"Backup '{name}' deleted.")
    return redirect('backup:backup_list')
