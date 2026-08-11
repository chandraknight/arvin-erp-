import gzip
import json
import os
import subprocess
import tempfile
from datetime import datetime

from django.apps import apps as django_apps
from django.conf import settings
from django.core import serializers
from django.db import connection, transaction

from .models import BackupRecord

BACKUP_DIR = os.path.join(settings.MEDIA_ROOT, 'backups')

# Models excluded from company backup (auth infrastructure, not tenant data)
_EXCLUDE_MODELS = {
    'accounts.User',
    'api.APIToken',
    'backup.BackupRecord',
}

# Models with direct company FK — auto-discovered at import time
def _company_scoped_models():
    from apps.company.models import Company
    result = []
    for model in django_apps.get_models():
        key = f"{model._meta.app_label}.{model.__name__}"
        if key in _EXCLUDE_MODELS:
            continue
        for field in model._meta.get_fields():
            if (
                hasattr(field, 'related_model')
                and field.related_model is Company
                and hasattr(field, 'column')
            ):
                result.append(model)
                break
    return result


def _ensure_backup_dir(subdir=''):
    path = os.path.join(BACKUP_DIR, subdir) if subdir else BACKUP_DIR
    os.makedirs(path, exist_ok=True)
    return path


def _db_settings():
    return settings.DATABASES['default']


def _db_engine():
    engine = _db_settings().get('ENGINE', '')
    if 'mysql' in engine:
        return 'mysql'
    if 'postgresql' in engine or 'postgis' in engine or 'cockroach' in engine:
        return 'postgresql'
    return engine


# ── Company backup ────────────────────────────────────────────────────────────

def create_company_backup(company, user):
    record = BackupRecord.objects.create(
        backup_type='COMPANY',
        company=company,
        file_name='',
        file_path='',
        status='PENDING',
        created_by=user,
    )
    try:
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        fname = f"company_{company.id}_{ts}.json.gz"
        dest = _ensure_backup_dir(f"company/{company.id}")
        fpath = os.path.join(dest, fname)

        objects = []
        for model in _company_scoped_models():
            qs = model.objects.filter(company=company)
            objects.extend(qs)

        data = serializers.serialize('json', objects, indent=2)

        with gzip.open(fpath, 'wt', encoding='utf-8') as f:
            f.write(data)

        size = os.path.getsize(fpath)
        record.file_name = fname
        record.file_path = fpath
        record.file_size = size
        record.status = 'COMPLETED'
        record.save(update_fields=['file_name', 'file_path', 'file_size', 'status'])
    except Exception as exc:
        record.status = 'FAILED'
        record.notes = str(exc)
        record.save(update_fields=['status', 'notes'])
        raise
    return record


def restore_company_backup(record, user):
    if record.status != 'COMPLETED' or not os.path.exists(record.file_path):
        raise ValueError("Backup file not available.")
    if record.backup_type != 'COMPANY':
        raise ValueError("Not a company backup.")

    company = record.company

    with transaction.atomic():
        # Delete existing company data in reverse dependency order
        for model in reversed(_company_scoped_models()):
            model.objects.filter(company=company).delete()

        with gzip.open(record.file_path, 'rt', encoding='utf-8') as f:
            data = f.read()

        for obj in serializers.deserialize('json', data):
            # skip if company mismatch (safety)
            instance = obj.object
            if hasattr(instance, 'company_id') and str(instance.company_id) != str(company.id):
                continue
            obj.save()


# ── Full database backup (Super Admin) ───────────────────────────────────────

def _pg_backup(db, fpath):
    env = os.environ.copy()
    env['PGPASSWORD'] = db.get('PASSWORD', '')
    cmd = [
        'pg_dump',
        '-h', db.get('HOST', 'localhost'),
        '-p', str(db.get('PORT', 5432)),
        '-U', db.get('USER', 'postgres'),
        '-F', 'c',
        '-f', fpath,
        db.get('NAME', 'erp'),
    ]
    result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        raise RuntimeError(f"pg_dump failed: {result.stderr.strip()}")


def _pg_restore(db, fpath):
    env = os.environ.copy()
    env['PGPASSWORD'] = db.get('PASSWORD', '')
    cmd = [
        'pg_restore',
        '-h', db.get('HOST', 'localhost'),
        '-p', str(db.get('PORT', 5432)),
        '-U', db.get('USER', 'postgres'),
        '-d', db.get('NAME', 'erp'),
        '--clean',
        '--if-exists',
        '--no-owner',
        # Run the whole restore as one transaction: if anything fails partway
        # through, Postgres rolls back everything instead of leaving the
        # database half-dropped/half-restored (which is what silently broke
        # login/sessions after a bad upload previously — --clean had already
        # dropped tables before the failure, and nothing rolled it back).
        '--single-transaction',
        fpath,
    ]
    result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=600)
    # With --single-transaction, a non-zero exit reliably means the whole
    # restore was rolled back — no more guessing from stderr wording.
    if result.returncode != 0:
        raise RuntimeError(f"pg_restore failed (rolled back, no changes applied): {result.stderr.strip()}")


def _mysql_backup(db, fpath):
    # Write password to a temp file in /tmp — never inside MEDIA_ROOT
    fd, cnf = tempfile.mkstemp(suffix='.cnf', prefix='erp_mysql_')
    try:
        with os.fdopen(fd, 'w') as f:
            f.write('[client]\n')
            f.write(f"password={db.get('PASSWORD', '')}\n")
        os.chmod(cnf, 0o600)
        cmd = [
            'mysqldump',
            f"--defaults-extra-file={cnf}",
            '-h', db.get('HOST', 'localhost'),
            '-P', str(db.get('PORT', 3306)),
            '-u', db.get('USER', 'root'),
            '--single-transaction',
            '--routines',
            '--triggers',
            '--result-file', fpath,
            db.get('NAME', 'erp'),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            raise RuntimeError(f"mysqldump failed: {result.stderr.strip()}")
    finally:
        if os.path.exists(cnf):
            os.remove(cnf)


def _mysql_restore(db, fpath):
    fd, cnf = tempfile.mkstemp(suffix='.cnf', prefix='erp_mysql_')
    try:
        with os.fdopen(fd, 'w') as f:
            f.write('[client]\n')
            f.write(f"password={db.get('PASSWORD', '')}\n")
        os.chmod(cnf, 0o600)
        with open(fpath, 'rb') as sql_file:
            cmd = [
                'mysql',
                f"--defaults-extra-file={cnf}",
                '-h', db.get('HOST', 'localhost'),
                '-P', str(db.get('PORT', 3306)),
                '-u', db.get('USER', 'root'),
                db.get('NAME', 'erp'),
            ]
            result = subprocess.run(cmd, stdin=sql_file, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            raise RuntimeError(f"mysql restore failed: {result.stderr.strip()}")
    finally:
        if os.path.exists(cnf):
            os.remove(cnf)


# Scratch MariaDB instance used only to stage a prod (MariaDB) dump so
# pgloader has a live server to read from — pgloader cannot parse raw .sql
# dump files directly. Kept on its own socket/port to avoid clashing with
# any other locally installed MySQL-family server.
_SCRATCH_MARIADB_SOCKET = '/tmp/mariadb.sock'
_SCRATCH_MARIADB_PORT = '3307'


def _mysql_load_dump_to_scratch_db(fpath, scratch_db_name):
    """Load a raw MySQL/MariaDB .sql dump into a fresh scratch MariaDB database."""
    base_args = ['mysql', '--socket', _SCRATCH_MARIADB_SOCKET, '-u', 'root']
    create_cmd = base_args + ['-e', f"DROP DATABASE IF EXISTS `{scratch_db_name}`; CREATE DATABASE `{scratch_db_name}`;"]
    result = subprocess.run(create_cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(f"Could not create scratch MariaDB database: {result.stderr.strip()}")

    with open(fpath, 'rb') as sql_file:
        load_cmd = base_args + [scratch_db_name]
        result = subprocess.run(load_cmd, stdin=sql_file, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        raise RuntimeError(f"Loading dump into scratch MariaDB database failed: {result.stderr.strip()}")


def _mysql_drop_scratch_db(scratch_db_name):
    subprocess.run(
        ['mysql', '--socket', _SCRATCH_MARIADB_SOCKET, '-u', 'root', '-e', f"DROP DATABASE IF EXISTS `{scratch_db_name}`;"],
        capture_output=True, text=True, timeout=60,
    )


def _pgloader_migrate(db, scratch_db_name):
    """Migrate the scratch MariaDB database into the target Postgres database via pgloader."""
    pg_uri = f"postgresql://{db.get('USER', 'postgres')}:{db.get('PASSWORD', '')}@{db.get('HOST', 'localhost')}:{db.get('PORT', 5432)}/{db.get('NAME', 'erp')}"
    mysql_uri = f"mysql://root@localhost:{_SCRATCH_MARIADB_PORT}/{scratch_db_name}"
    result = subprocess.run(
        ['pgloader', mysql_uri, pg_uri],
        capture_output=True, text=True, timeout=1800,
    )
    if result.returncode != 0:
        raise RuntimeError(f"pgloader migration failed: {result.stderr.strip() or result.stdout.strip()}")


def _mysql_to_postgresql_restore(db, fpath):
    scratch_db_name = f"erp_restore_scratch_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    try:
        _mysql_load_dump_to_scratch_db(fpath, scratch_db_name)
        _pgloader_migrate(db, scratch_db_name)
    finally:
        _mysql_drop_scratch_db(scratch_db_name)


def create_full_backup(user):
    record = BackupRecord.objects.create(
        backup_type='FULL',
        file_name='',
        file_path='',
        status='PENDING',
        created_by=user,
    )
    try:
        db = _db_settings()
        engine = _db_engine()
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')

        if engine == 'mysql':
            fname = f"full_db_{ts}.sql"
        else:
            fname = f"full_db_{ts}.dump"

        dest = _ensure_backup_dir('full')
        fpath = os.path.join(dest, fname)

        if engine == 'mysql':
            _mysql_backup(db, fpath)
        elif engine == 'postgresql':
            _pg_backup(db, fpath)
        else:
            raise RuntimeError(f"Unsupported database engine for full backup: {engine}")

        size = os.path.getsize(fpath)
        record.file_name = fname
        record.file_path = fpath
        record.file_size = size
        record.status = 'COMPLETED'
        record.notes = engine
        record.save(update_fields=['file_name', 'file_path', 'file_size', 'status', 'notes'])
    except Exception as exc:
        record.status = 'FAILED'
        record.notes = str(exc)
        record.save(update_fields=['status', 'notes'])
        raise
    return record


def _sniff_dump_engine(fpath):
    """Detect a dump file's origin engine from its content, not its extension."""
    with open(fpath, 'rb') as f:
        head = f.read(4096)
    if head.startswith(b'PGDMP'):
        return 'postgresql'
    if b'MySQL dump' in head or b'-- MySQL' in head or b'MariaDB dump' in head:
        return 'mysql'
    if b'PostgreSQL database dump' in head:
        return 'postgresql'
    return None


def restore_full_backup(record, user):
    if record.status != 'COMPLETED' or not os.path.exists(record.file_path):
        raise ValueError("Backup file not available.")
    if record.backup_type != 'FULL':
        raise ValueError("Not a full backup.")

    db = _db_settings()
    configured_engine = _db_engine()

    dump_engine = _sniff_dump_engine(record.file_path)
    if dump_engine is None:
        # Fall back to extension only when content sniffing is inconclusive.
        if record.file_path.endswith('.sql'):
            dump_engine = 'mysql'
        elif record.file_path.endswith('.dump'):
            dump_engine = 'postgresql'

    if dump_engine != configured_engine:
        if dump_engine == 'mysql' and configured_engine == 'postgresql':
            _mysql_to_postgresql_restore(db, record.file_path)
            return
        raise RuntimeError(
            f"Backup file appears to be a {dump_engine or 'unknown'} dump, "
            f"but this server is configured for {configured_engine}, and no "
            f"automatic conversion path exists for that direction. Restore aborted."
        )
    engine = dump_engine

    if engine == 'mysql':
        _mysql_restore(db, record.file_path)
    elif engine == 'postgresql':
        _pg_restore(db, record.file_path)
    else:
        raise RuntimeError(f"Cannot determine restore method for file: {record.file_name}")


def delete_backup(record):
    if record.file_path and os.path.exists(record.file_path):
        os.remove(record.file_path)
    record.delete()


# Extensions accepted for an uploaded full-DB dump, mapped to the restore
# engine that will handle them (matches restore_full_backup's own detection).
UPLOAD_EXTENSIONS = {'.dump': 'postgresql', '.sql': 'mysql'}
MAX_UPLOAD_SIZE = 2 * 1024 * 1024 * 1024  # 2 GB


def save_uploaded_backup(uploaded_file, user):
    """
    Persist an admin-uploaded dump file as a FULL BackupRecord so it can go
    through the existing (confirm-then-restore) restore flow untouched.
    Never trusts the uploaded filename beyond its extension — writes under a
    freshly generated name to avoid path traversal / overwrite tricks.
    """
    ext = os.path.splitext(uploaded_file.name)[1].lower()
    if ext not in UPLOAD_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type '{ext or '(none)'}'. Upload a PostgreSQL "
            f".dump (from pg_dump -F c) or MySQL .sql file."
        )
    if uploaded_file.size > MAX_UPLOAD_SIZE:
        raise ValueError(f"File too large ({uploaded_file.size / (1024**3):.2f} GB). Max is 2 GB.")

    engine = UPLOAD_EXTENSIONS[ext]
    record = BackupRecord.objects.create(
        backup_type='FULL',
        file_name='',
        file_path='',
        status='PENDING',
        created_by=user,
        notes=f'{engine} (uploaded)',
    )
    try:
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        fname = f"uploaded_{ts}{ext}"
        dest = _ensure_backup_dir('full')
        fpath = os.path.join(dest, fname)

        with open(fpath, 'wb') as out:
            for chunk in uploaded_file.chunks():
                out.write(chunk)

        record.file_name = fname
        record.file_path = fpath
        record.file_size = os.path.getsize(fpath)
        record.status = 'COMPLETED'
        record.save(update_fields=['file_name', 'file_path', 'file_size', 'status'])
    except Exception as exc:
        record.status = 'FAILED'
        record.notes = str(exc)
        record.save(update_fields=['status', 'notes'])
        raise
    return record
