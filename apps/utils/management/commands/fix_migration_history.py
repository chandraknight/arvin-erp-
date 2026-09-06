"""
Detects and repairs "inconsistent migration history" gaps in the
django_migrations table — cases where a migration is recorded as applied
but one of its declared dependencies is not, which makes Django's
`migrate` (and anything that loads the migration graph) refuse to run
with `InconsistentMigrationHistory`.

This project has hit this repeatedly after branch merges: two migration
files end up sharing the same numeric prefix across a merge (e.g. two
different `products/0024_*.py` in different history lines), and the
`django_migrations` table on a given database ends up with a row for a
migration whose dependency's row never got inserted — even though the
dependency's schema changes were, in fact, already applied to that
database under an older, now-replaced migration file.

We do NOT touch any migration .py files (never allowed — see CLAUDE.md).
We only insert missing bookkeeping rows into django_migrations, and only
after confirming the "gap" migration is on disk with the exact
dependency reference, so this stays a metadata repair, not a schema
change.

Usage:
    python manage.py fix_migration_history            # dry run, reports gaps
    python manage.py fix_migration_history --apply     # inserts missing rows
"""
from django.core.management.base import BaseCommand
from django.db import connection
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.recorder import MigrationRecorder


class Command(BaseCommand):
    help = (
        "Detect (and optionally fix) django_migrations rows whose recorded "
        "dependency is missing, which causes InconsistentMigrationHistory."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply', action='store_true',
            help='Actually insert the missing dependency rows. Without this flag, only reports gaps.',
        )

    def handle(self, *args, **options):
        apply_fix = options['apply']

        recorder = MigrationRecorder(connection)
        recorded = recorder.applied_migrations()  # {(app, name): ...} — actually a set of tuples

        # Disk-only loader: build the graph without touching the DB's
        # consistency check, so we can inspect dependencies freely even
        # while the real graph is inconsistent.
        loader = MigrationLoader(None, ignore_no_migrations=True)
        disk = loader.disk_migrations  # {(app, name): Migration}

        gaps = []
        for key in recorded:
            app, name = key
            mig = disk.get((app, name))
            if not mig:
                # Recorded migration whose file no longer exists on disk at
                # all (renamed/squashed) — nothing we can safely infer here.
                continue
            for dep_app, dep_name in mig.dependencies:
                if dep_app in ('__first__',) or dep_name == '__first__':
                    continue
                if (dep_app, dep_name) in recorded:
                    continue
                if (dep_app, dep_name) not in disk:
                    # Dependency doesn't exist on disk either — not our
                    # class of bug, skip.
                    continue
                gaps.append((app, name, dep_app, dep_name))

        if not gaps:
            self.stdout.write(self.style.SUCCESS(
                "No migration history gaps found — django_migrations is consistent "
                "with every recorded migration's declared dependencies."
            ))
            return

        self.stdout.write(self.style.WARNING(
            f"Found {len(gaps)} migration history gap(s):"
        ))
        for app, name, dep_app, dep_name in gaps:
            self.stdout.write(
                f"  {app}.{name} is recorded as applied, but its dependency "
                f"{dep_app}.{dep_name} is NOT recorded as applied."
            )

        if not apply_fix:
            self.stdout.write(self.style.NOTICE(
                "\nDry run only — no changes made. Re-run with --apply to insert "
                "the missing dependency rows (timestamped just before the "
                "migration that depends on them)."
            ))
            return

        with connection.cursor() as cursor:
            for app, name, dep_app, dep_name in gaps:
                # Look up the applied timestamp of the migration that depends
                # on the missing row, so we can backdate the inserted row to
                # just before it — keeping migration history in a plausible
                # chronological order.
                cursor.execute(
                    "SELECT applied FROM django_migrations WHERE app = %s AND name = %s",
                    [app, name],
                )
                row = cursor.fetchone()
                applied_at = row[0] if row else None

                cursor.execute(
                    "SELECT 1 FROM django_migrations WHERE app = %s AND name = %s",
                    [dep_app, dep_name],
                )
                if cursor.fetchone():
                    # Already inserted by an earlier iteration (e.g. two
                    # gaps sharing the same dependency).
                    continue

                if applied_at is not None:
                    cursor.execute(
                        "INSERT INTO django_migrations (app, name, applied) VALUES (%s, %s, %s)",
                        [dep_app, dep_name, applied_at],
                    )
                else:
                    cursor.execute(
                        "INSERT INTO django_migrations (app, name, applied) VALUES (%s, %s, now())",
                        [dep_app, dep_name],
                    )
                self.stdout.write(self.style.SUCCESS(
                    f"  Inserted missing row: {dep_app}.{dep_name}"
                ))

        self.stdout.write(self.style.SUCCESS(
            "\nDone. Re-run `python manage.py showmigrations` / `migrate` to confirm."
        ))
