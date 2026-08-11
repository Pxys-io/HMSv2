# Phase 01 — Scaffold

**Revision 2.0:** the scaffold now establishes safe token/cookie handling,
idempotency infrastructure, public-asset separation, and the single-process
SSE constraint before domain work begins.

**Goal:** a runnable monorepo skeleton: backend venv, two Vite apps, dual Alembic
configs, dev script, lint/format. Nothing user-facing yet.

**Depends on:** nothing. **Blocks:** every other phase.

---

## 1. Deliverables

- Final monorepo directory layout (per PLAN.md §3)
- Backend: pinned dependencies, `pydantic-settings` config, `.env` handling, app factory
- Two Alembic environments: `backend/alembic/` (main DB) + `backend/alembic_audit/` (audit DB)
- `web-staff/` and `web-public/` Vite + React 18 + TS apps with Tailwind v4, react-router, TanStack Query, i18next, fonts
- `scripts/dev.sh` (one command starts all three) and `scripts/reset-dev.sh` (wipe + re-migrate + seed-empty)
- Lint/format: `ruff` (Python), `eslint` + `prettier` (TS), pre-commit hooks optional
- Root `.gitignore` covering venv, node_modules, dist, uploads, *.db, .env

## 2. Step-by-step

### 2.1 Root & backend base

1. Create directories exactly as PLAN.md §3 (including empty `deploy/systemd|nginx|scripts`, `scripts/`).
2. Root `.gitignore`: `.venv/`, `__pycache__/`, `*.pyc`, `node_modules/`, `dist/`, `.env`, `.env.*`, `!.env.example`, `uploads/`, `*.db`, `*.db-journal`, `.ruff_cache/`, `.pytest_cache/`, `*.tsbuildinfo`.
3. `backend/requirements.txt` — pin:
   ```
   fastapi==0.115.6
   uvicorn[standard]==0.34.0
   sqlalchemy==2.0.36
   alembic==1.14.0
   pydantic==2.10.4
   pydantic-settings==2.7.0
   PyJWT==2.10.1
   cryptography==44.0.0
   pwdlib[argon2]==0.2.1
   python-multipart==0.0.20
   aiosmtplib==3.0.2
   psycopg[binary]==3.2.3
   Pillow==11.0.0
   pypdf==5.1.0
   python-magic==0.4.27
   sse-starlette==2.2.1
   slowapi==0.1.9
   httpx==0.28.1
   pytest==8.3.4
   pytest-asyncio==0.25.0
   ruff==0.8.4
   ```
   (Versions may be bumped at execution time; keep `requirements.txt` the single source of truth.)
4. `python -m venv backend/.venv && pip install -r requirements.txt`.
5. `backend/app/core/config.py` — `Settings(BaseSettings)` with:
   - `APP_ENV` (`dev|prod`), `SECRET_KEY`, `TOKEN_ALG=HS256`
   - `DATABASE_URL` = `sqlite:///./hmsv2.db`
   - `AUDIT_DATABASE_URL` = `sqlite:///./hmsv2_audit.db`
   - `CLINIC_TZ` = `Africa/Cairo`, `CURRENCY` = `EGP`
   - `UPLOAD_DIR` = `./uploads`, `MAX_UPLOAD_MB` = 15
   - `CORS_STAFF_ORIGINS` = `["http://localhost:5173"]`, `CORS_PUBLIC_ORIGINS` = `["http://localhost:5174"]`
   - `SMTP_*` (host/port/user/pass/from; empty = email disabled, log instead)
   - `ACCESS_COOKIE_NAME`, `REFRESH_COOKIE_NAME`, `COOKIE_SECURE`, `COOKIE_SAMESITE`, `CSRF_COOKIE_NAME`
   - `ACCESS_TOKEN_MINUTES_STAFF=30`, `REFRESH_TOKEN_DAYS_STAFF=30`, `ACCESS_TOKEN_MINUTES_PATIENT=30`, `REFRESH_TOKEN_DAYS_PATIENT=60`
   - `IDEMPOTENCY_TTL_DAYS=7`, `AUDIT_CHECKPOINT_PRIVATE_KEY_PATH`, `AUDIT_CHECKPOINT_DIR`
   - `CLAMAV_SOCKET` (required in production; empty in local development only)
   - `FIELD_ENCRYPTION_KEY` (required for encrypted national-ID fields in production)
   - `RATE_LIMIT_PUBLIC` = `60/minute`
   - `.env` file support; `backend/.env.example` committed with all keys documented.
6. Refactor `backend/app/main.py` into an app factory `create_app()`; keep `/api/health` returning `{ "status": "ok", "version": ..., "env": ... }`. CORS allows only the exact staff and public origins from settings; route authorization, not CORS, enforces staff/public separation. Add request-id and CSRF middleware now so later routes cannot forget them.
7. `backend/run.py` stays the dev entrypoint (uvicorn reload on port 8000).

### 2.2 Dual databases + Alembic

8. `backend/app/db/base.py` — two declarative bases: `Base` (main) and `AuditBase` (audit). Two engines/sessions in `backend/app/db/session.py`: `engine`, `SessionLocal`, `audit_engine`, `AuditSessionLocal` + FastAPI deps `get_db()`, `get_audit_db()`.
9. `backend/alembic/` — standard `alembic init` adapted: `env.py` reads `DATABASE_URL` from app settings, `target_metadata = Base.metadata`.
10. `backend/alembic_audit/` — second, independent `alembic init` (own `alembic.ini` section or own ini file `alembic_audit.ini`), `target_metadata = AuditBase.metadata`.
11. Document commands in the root `README.md`, this phase's execution notes, and `scripts/dev.sh` comments:
    - `alembic upgrade head` (main)
    - `alembic -c alembic_audit.ini upgrade head` (audit)
12. Verify: both SQLite files created by a trivial initial migration each (`create extension`/no-op is fine; main gets `setting` table in phase 02 — for now a `schema_meta` placeholder is acceptable but prefer empty initial revision).
13. Add a main-database `idempotency_key` table and a `public_asset` table to the phase-01 migration so replay protection and public doctor/clinic images have a stable home before feature routes exist.

### 2.3 Frontend scaffolding (×2)

For **each** of `web-staff` and `web-public`:

14. `npm create vite@latest <dir> -- --template react-ts`, then install and wire:
    - `tailwindcss @tailwindcss/vite` (v4), `clsx`, `tailwind-merge`
    - `react-router-dom` v6, `@tanstack/react-query` v5
    - `react-i18next i18next` (namespaces per Plan/12)
    - `@fontsource/inter`, `@fontsource/ibm-plex-sans-arabic`, `@fontsource/ibm-plex-mono`
    - `lucide-react`, `sonner`, `dayjs`
    - `react-hook-form`, `zod`, `@hookform/resolvers`
    - `zustand`
    - dev: `eslint`, `prettier`, `typescript-eslint`
15. `web-staff` additionally: Radix primitives used by Plan/00 §6.1 (`@radix-ui/react-dialog`, `-popover`, `-dropdown-menu`, `-tabs`, `-tooltip`, `-select`, `-scroll-area`, `-switch`, `-checkbox`, `-radio-group`), plus `cmdk` (command palette).
16. `web-public` additionally: nothing heavy; keep the bundle lean (it is a marketing site).
17. Configure dev servers: staff `5173`, public `5174`; both proxy `/api` → `http://localhost:8000` in `vite.config.ts` with `changeOrigin`, cookie-path/domain rewriting for local development, and credential forwarding (avoids CORS in dev; prod uses nginx).
18. Design tokens: create `src/styles/tokens.css` in each app implementing Plan/00 §2–4 as CSS variables + Tailwind theme mapping (`bg-surface`, `text-ink-600`, `border-border`, `bg-brand-600`…). This is the only place hex values may appear.
19. Each app renders a placeholder home page (name + health-check call to `/api/health` showing `ok`).

### 2.4 Scripts & quality gates

20. `scripts/dev.sh` (chmod +x):
    - start backend: `cd backend && .venv/bin/python run.py`
    - start staff: `npm run dev --prefix web-staff`
    - start public: `npm run dev --prefix web-public`
    - run all in parallel, trap Ctrl-C to kill children; print URLs.
21. `scripts/reset-dev.sh`: stop servers, delete `backend/*.db`, `rm -rf backend/uploads/*`, run both alembic upgrades, print "clean dev DB ready".
22. `ruff` config in `backend/pyproject.toml` (`line-length = 100`, target `py312`); eslint+prettier configs per app; add root `Makefile`? — **No.** Keep scripts in `scripts/` only (owner dislikes extra tooling).
23. Test tooling: add `vitest`, `jsdom`, `@testing-library/react`, `@testing-library/jest-dom`, and `@testing-library/user-event` to both apps. Smoke test files: `backend/tests/test_health.py` (asserts 200 + payload keys); each app: one render test.

## 3. UI/UX in this phase

None beyond placeholder pages — but the **token files (§2.3 step 17) must be
complete and match Plan/00 exactly**, because every later phase builds on them.

## 4. Tests

- `pytest backend/tests/test_health.py` passes.
- `npm run test --prefix web-staff` and `web-public` pass (render smoke).
- `ruff check backend` and `eslint` clean on scaffolded code.

## 5. Done-when checklist

- [ ] `scripts/dev.sh` starts backend (8000), staff (5173), public (5174) with one command
- [ ] `GET /api/health` → 200 `{status:"ok"}`; both apps display it
- [ ] `alembic upgrade head` and `alembic -c alembic_audit.ini upgrade head` both succeed on empty SQLite
- [ ] `scripts/reset-dev.sh` produces clean databases
- [ ] Tokens CSS matches Plan/00 (spot-check 5 variables)
- [ ] No Docker files exist anywhere in the repo
- [ ] No access or refresh token is persisted in localStorage; the client contract uses memory access tokens plus HttpOnly refresh cookies
- [ ] `psycopg` and `python-magic` are installed from the pinned requirements
- [ ] `git status` clean after commit of scaffold (no node_modules/venv/db tracked)

## 6. Gotchas

- **Two Alembic setups**: keep them fully independent; never import `Base` in audit env or vice versa.
- Tailwind v4 is CSS-first config (`@theme` in CSS), not `tailwind.config.js` — follow v4 docs.
- `@fontsource/ibm-plex-sans-arabic` needs explicit weight imports (400/500/600/700).
- Vite proxy means dev CORS is a non-issue; still configure CORS correctly for prod now.
