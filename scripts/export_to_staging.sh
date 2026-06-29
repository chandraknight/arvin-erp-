#!/usr/bin/env bash
# Export local data + media and push to staging server.
# Usage:  bash scripts/export_to_staging.sh [staging_user@host]
# Default host: snsstagi@s1316.sgp1.myftp.org

set -euo pipefail

STAGING="${1:-snsstagi@s1316.sgp1.myftp.org}"
REMOTE_APP="/home/snsstagi/erp-api"
DUMP_DIR="/tmp/erp_staging_export"
FIXTURE_DIR="$DUMP_DIR/fixtures"

echo "==> Exporting to: $STAGING:$REMOTE_APP"
echo ""

# ── 1. Prepare local dump directory ──────────────────────────────────────────
rm -rf "$DUMP_DIR"
mkdir -p "$FIXTURE_DIR"

cd "$(dirname "$0")/.."   # project root

# ── 2. Dump data fixtures ─────────────────────────────────────────────────────
echo "[1/5] Dumping database fixtures..."

python manage.py dumpdata \
    products.CategoryType products.Category products.Product \
    products.ProductStock products.ProductImage \
    --indent 2 --output "$FIXTURE_DIR/01_products.json"

python manage.py dumpdata \
    ecom \
    --indent 2 --output "$FIXTURE_DIR/02_ecom.json"

python manage.py dumpdata \
    company.Company company.Branch company.FiscalYear \
    --indent 2 --output "$FIXTURE_DIR/03_company.json"

python manage.py dumpdata \
    customers.Customer \
    --indent 2 --output "$FIXTURE_DIR/04_customers.json"

python manage.py dumpdata \
    bookkeeping.LedgerAccount bookkeeping.LedgerOpeningBalance \
    --indent 2 --output "$FIXTURE_DIR/05_bookkeeping.json"

echo "    Fixtures written to $FIXTURE_DIR"
ls -lh "$FIXTURE_DIR"

# ── 3. Bundle media files ─────────────────────────────────────────────────────
echo ""
echo "[2/5] Bundling media files (products + company logos)..."
MEDIA_TAR="$DUMP_DIR/media.tar.gz"
tar -czf "$MEDIA_TAR" \
    -C "$(pwd)" \
    media/products \
    media/dps \
    $([ -d media/company_logos ] && echo media/company_logos || true)
echo "    Media archive: $(du -sh "$MEDIA_TAR" | cut -f1)"

# ── 4. Upload to staging ──────────────────────────────────────────────────────
echo ""
echo "[3/5] Uploading fixtures to $STAGING..."
rsync -avz --progress "$FIXTURE_DIR/" "$STAGING:$REMOTE_APP/fixtures/"

echo ""
echo "[4/5] Uploading media archive to $STAGING..."
rsync -avz --progress "$MEDIA_TAR" "$STAGING:$REMOTE_APP/media.tar.gz"

# ── 5. Run remote commands ────────────────────────────────────────────────────
echo ""
echo "[5/5] Running remote loaddata + media extract..."
ssh "$STAGING" bash <<REMOTE
set -euo pipefail
cd "$REMOTE_APP"
source .venv/bin/activate 2>/dev/null || source venv/bin/activate 2>/dev/null || true

echo "  -> Extracting media..."
tar -xzf media.tar.gz
rm media.tar.gz

echo "  -> Loading fixtures (order matters for FK constraints)..."
python manage.py loaddata fixtures/03_company.json
python manage.py loaddata fixtures/01_products.json
python manage.py loaddata fixtures/02_ecom.json
python manage.py loaddata fixtures/04_customers.json
python manage.py loaddata fixtures/05_bookkeeping.json

echo "  -> Collecting static files..."
python manage.py collectstatic --noinput --clear

echo ""
echo "Done! Staging data load complete."
REMOTE

echo ""
echo "==> Export + deploy complete."
echo "    Products, categories, images and ecom config are now on staging."
