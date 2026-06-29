#!/bin/bash
source /home/snsstagi/virtualenv/erp-api/3.11/bin/activate && cd /home/snsstagi/erp-api

# 1. Remove existing installed packages
pip uninstall -y -r requirements.production.txt

# 2. Clear pip cache
pip cache purge

TAG="$1"

if [ -z "$TAG" ]; then
    echo "No tag provided. Exiting."
    exit 1
fi

echo "✅ Checking out tag: $TAG"

git fetch --all --tags
git checkout "tags/$TAG" -f

# Optional: Clean pyc files
echo "🧹 Removing .pyc files..."
find . -name "*.pyc" -delete

echo "📦 Installing dependencies..."
pip install -r requirements.production.txt

pip install mysqlclient

echo "🛠️ Running migrations..."
python manage.py migrate

echo "📂 Collecting static files..."
python manage.py collectstatic --noinput

echo "🔄 Restarting server..."
mkdir -p tmp
touch tmp/restart.txt

echo "🚀 Deployment for tag $TAG completed."
deactivate