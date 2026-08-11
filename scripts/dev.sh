#!/usr/bin/env bash
# Start the full HMSv2 dev stack: backend API + both Vite apps.
# Ctrl-C stops everything.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "Starting HMSv2 dev stack..."
echo "  API:     http://localhost:8000"
echo "  Staff:   http://localhost:5173"
echo "  Public:  http://localhost:5174"

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
  cd "$ROOT/backend"
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
