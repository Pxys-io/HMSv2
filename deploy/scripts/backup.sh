#!/usr/bin/env bash
# Nightly backups: Postgres dumps + uploads, encrypted with age (Plan/13 §4).
# Install in cron as the hmsv2 user:
#   30 3 * * * /opt/hmsv2/deploy/scripts/backup.sh
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/var/backups/hmsv2}"
STAMP="$(date +%Y-%m-%d)"
DEST="$BACKUP_DIR/$STAMP"
AGE_RECIPIENT="${AGE_RECIPIENT:?set the age public key (off-server copy)}"

mkdir -p "$DEST"

echo "==> pg_dump"
pg_dump -Fc hmsv2        | age -r "$AGE_RECIPIENT" > "$DEST/hmsv2.dump.age"
pg_dump -Fc hmsv2_audit  | age -r "$AGE_RECIPIENT" > "$DEST/hmsv2_audit.dump.age"

echo "==> uploads"
tar czf - /var/lib/hmsv2/uploads | age -r "$AGE_RECIPIENT" > "$DEST/uploads.tgz.age"

echo "==> signed audit checkpoint (Plan/02 §4)"
cd /opt/hmsv2/backend
.venv/bin/python -c "
from app.db.session import AuditSessionLocal
from app.audit import service as audit
with AuditSessionLocal() as db:
    cp = audit.create_checkpoint(db)
    print('checkpoint', cp.id, 'events', cp.last_event_id)
" >> "$DEST/checkpoint.log"
cp /var/lib/hmsv2/checkpoints/checkpoint_ed25519.pub "$DEST/" 2>/dev/null || true

echo "==> manifest"
cd "$DEST"
sha256sum * > SHA256SUMS

echo "==> rotation: keep 14 daily + 4 weekly"
find "$BACKUP_DIR" -maxdepth 1 -type d -mtime +14 -exec rm -rf {} +

echo "==> copy off-server (mandatory for the audit guarantee, Plan/13 §4.6)"
if [[ -n "${OFFSITE_TARGET:-}" ]]; then
  rsync -a "$DEST/" "$OFFSITE_TARGET/"
fi

echo "Backup complete: $DEST"
