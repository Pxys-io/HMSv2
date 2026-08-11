#!/usr/bin/env bash
# Deploy a tagged commit (Plan/13 §3.1 step 10). Run as the hmsv2 user from
# the cloned repo. Rollback: git checkout <previous-tag> && re-run.
set -euo pipefail

TAG="${1:?usage: deploy.sh <git-tag>}"
cd /opt/hmsv2
REPO=/opt/hmsv2

echo "==> pull $TAG"
git fetch origin --tags
git checkout "$TAG"

echo "==> backend"
cd "$REPO/backend"
python3.12 -m venv .venv 2>/dev/null || true
.venv/bin/pip install -q -r requirements.txt
.venv/bin/alembic upgrade head
.venv/bin/alembic -c alembic_audit.ini upgrade head

echo "==> frontends"
cd "$REPO/web-staff"
npm ci --silent && npm run build
rsync -a --delete dist/ /var/www/hmsv2/staff/

cd "$REPO/web-public"
npm ci --silent && npm run build
rsync -a --delete dist/ /var/www/hmsv2/public/

echo "==> restart API"
systemctl restart hmsv2-api
sleep 2
curl -fsS http://127.0.0.1:8000/api/health

echo ""
echo "Deployed $TAG. Rollback: git checkout <previous-tag> && deploy.sh <previous-tag>"
