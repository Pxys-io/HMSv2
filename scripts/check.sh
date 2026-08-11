#!/usr/bin/env bash
# HMSv2 full check: lint -> typecheck -> tests -> builds -> live smoke.
# Everything in one command. Usage:
#   ./scripts/check.sh          # full pipeline incl. live smoke
#   ./scripts/check.sh --skip-live   # code checks only (no server boot)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
LIVE=1
[[ "${1:-}" == "--skip-live" ]] && LIVE=0

GREEN='\033[0;32m'; RED='\033[0;31m'; BOLD='\033[1m'; RESET='\033[0m'
ok()   { printf "${GREEN}${BOLD}✓${RESET} %s\n" "$1"; }
fail() { printf "${RED}${BOLD}✗${RESET} %s\n" "$1"; exit 1; }
section() { printf "\n${BOLD}== %s ==${RESET}\n" "$1"; }

cd "$ROOT"

# ---------------------------------------------------------------- backend
section "Backend — lint + tests"
(cd "$BACKEND" && .venv/bin/ruff check app tests) || fail "ruff failed"
ok "ruff clean"
(cd "$BACKEND" && .venv/bin/pytest -q) || fail "backend tests failed"
ok "backend tests passed"

# ---------------------------------------------------------------- frontends
for app in web-staff web-public; do
  section "$app — typecheck + lint + tests + build"
  (cd "$ROOT/$app" && npx tsc -b) || fail "$app typecheck failed"
  ok "$app typecheck"
  (cd "$ROOT/$app" && npx eslint .) || fail "$app lint failed"
  ok "$app lint"
  (cd "$ROOT/$app" && npx vitest run) || fail "$app tests failed"
  ok "$app tests"
  (cd "$ROOT/$app" && npm run build) || fail "$app build failed"
  ok "$app build"
done

# ---------------------------------------------------------------- live smoke
if [[ "$LIVE" == 1 ]]; then
  section "Live end-to-end smoke"
  # fresh dev databases + seed
  "$ROOT/scripts/reset-dev.sh" >/dev/null
  (cd "$BACKEND" && .venv/bin/python -m app.seed >/dev/null)

  # boot the API
  if lsof -ti tcp:8000 >/dev/null 2>&1; then
    echo "  port 8000 busy — using the running API"
  else
    (cd "$BACKEND" && .venv/bin/python run.py >/tmp/hmsv2-smoke.log 2>&1 &)
    for _ in $(seq 1 30); do
      curl -fsS http://localhost:8000/api/health >/dev/null 2>&1 && break
      sleep 0.5
    done
  fi
  curl -fsS http://localhost:8000/api/health >/dev/null 2>&1 || fail "API did not start"

  (cd "$ROOT" && python3 scripts/smoke.py) || fail "live smoke failed"
  ok "live smoke passed"

  # cleanup
  if lsof -ti tcp:8000 >/dev/null 2>&1; then
    lsof -ti tcp:8000 | xargs -r kill 2>/dev/null || true
  fi
fi

echo ""
printf "${GREEN}${BOLD}All checks passed ✓${RESET}\n"
