#!/usr/bin/env bash
# Wipe local dev databases + uploads and rebuild from migrations.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"

echo "Stopping anything on :8000 (backend dev server) if running..."
lsof -ti tcp:8000 | xargs -r kill 2>/dev/null || true

rm -f "$BACKEND/hmsv2.db" "$BACKEND/hmsv2_audit.db"
rm -rf "$BACKEND/uploads"
mkdir -p "$BACKEND/uploads"

cd "$BACKEND"
.venv/bin/alembic upgrade head
.venv/bin/alembic -c alembic_audit.ini upgrade head

echo ""
echo "Clean dev databases ready."
