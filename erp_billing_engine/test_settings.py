"""
Test settings — inherits from main settings.

Changes:
- MIGRATION_MODULES: sets bookkeeping to None so Django uses syncdb instead
  of running migration 0009 (which installs PL/pgSQL triggers via
  schema_editor.execute — psycopg2 chokes on % signs in RAISE EXCEPTION
  strings). All bookkeeping tables are still created via syncdb.
  The PL/pgSQL layer is not needed for Django-level unit/integration tests.
"""
from erp_billing_engine.settings import *  # noqa: F401, F403

DATABASES['default']['TEST'] = {
    'NAME': 'test_erp_db_qa',
}
