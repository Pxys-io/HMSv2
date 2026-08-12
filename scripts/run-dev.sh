#!/usr/bin/env bash
# One-command dev runner: migrate DB -> seed (creates admin if missing) ->
# start backend + both Vite apps. Ctrl-C stops everything.
#
#   ./scripts/run-dev.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"

if [[ ! -x "$BACKEND/.venv/bin/python" ]]; then
  echo "ERROR: backend venv missing. Run:"
  echo "  cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi

echo "== 1/4 Migrating databases =="
(cd "$BACKEND" && .venv/bin/alembic upgrade head)
(cd "$BACKEND" && .venv/bin/alembic -c alembic_audit.ini upgrade head)

echo "== 2/4 Seeding (idempotent; admin created only if missing) =="
(cd "$BACKEND" && .venv/bin/python -m app.seed)

echo "== 3/4 Starting HMSv2 dev stack =="
echo "  API:     http://localhost:8000"
echo "  Staff:   http://localhost:5173"
echo "  Public:  http://localhost:5174"
echo "  Admin login (dev): admin@example.com / admin12345"

pids=()
cleanup() {
  echo ""
  echo "Stopping dev servers..."
  for pid in "${pids[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
}
trap cleanup EXIT INT TERM

(
  cd "$BACKEND"
  exec .venv/bin/python run.py
) &
pids+=($!)

(
  cd "$ROOT/web-staff"
  exec npm run dev
) &
pids+=($!)

(
  cd "$ROOT/web-public"
  exec npm run dev
) &
pids+=($!)

wait
