#!/usr/bin/env bash
# HMSv2 VPS bootstrap (Ubuntu 24.04, no Docker).
# Run as root. Replace clinic.example with the real domains before running.
set -euo pipefail

DOMAIN_PUBLIC="${DOMAIN_PUBLIC:-clinic.example}"
DOMAIN_STAFF="${DOMAIN_STAFF:-app.clinic.example}"
DOMAIN_API="${DOMAIN_API:-api.clinic.example}"
APP_USER=hmsv2

echo "==> System packages"
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
  postgresql nginx certbot python3.12-venv libmagic1 age ufw curl

echo "==> Service user + directories"
id -u "$APP_USER" >/dev/null 2>&1 || useradd -r -m -s /bin/bash "$APP_USER"
mkdir -p /var/www/hmsv2/public /var/www/hmsv2/staff /var/lib/hmsv2/uploads /var/lib/hmsv2/checkpoints /var/backups/hmsv2 /opt/hmsv2
chown -R "$APP_USER:$APP_USER" /var/www/hmsv2 /var/lib/hmsv2 /opt/hmsv2

echo "==> PostgreSQL databases"
sudo -u postgres psql -c "CREATE ROLE hmsv2 LOGIN PASSWORD 'CHANGE_ME';" 2>/dev/null || true
sudo -u postgres createdb -O hmsv2 hmsv2 2>/dev/null || true
sudo -u postgres createdb -O hmsv2 hmsv2_audit 2>/dev/null || true

echo "==> Firewall"
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

echo ""
echo "Next steps (manual, documented in Plan/13):"
echo "  1. Create /opt/hmsv2/backend/.env (from .env.example) as $APP_USER"
echo "  2. python3.12 -m venv .venv && pip install -r requirements.txt"
echo "  3. alembic upgrade head + alembic -c alembic_audit.ini upgrade head"
echo "  4. Install deploy/systemd/hmsv2-api.service"
echo "  5. Install deploy/nginx/*.conf with real domains"
echo "  6. certbot --nginx -d $DOMAIN_PUBLIC -d $DOMAIN_STAFF -d $DOMAIN_API"
echo "  7. Install deploy/scripts/backup.sh in cron"
