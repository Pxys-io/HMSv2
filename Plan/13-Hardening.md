# Phase 13 — Hardening & Production Launch

**Revision 2.0:** production deployment now matches the single-process SSE
design, treats audit reconciliation/checkpoints as launch requirements, and
adds explicit controls for cookies, clinical files, backups, and device data.

**Goal:** take the finished system to a plain VPS — securely, reproducibly,
with backups — and run the pre-launch checklist. **No Docker, ever.**

**Depends on:** all previous. **Blocks:** go-live.

---

## 1. Deliverables

- `deploy/`: systemd units, nginx vhosts, backup scripts, VPS bootstrap script
- Security pass: rate limits, headers, CORS lockdown, secrets hygiene
- Backup/restore drill executed and documented
- Full test suites green + launch checklist signed

## 2. Production topology (single VPS)

```
nginx (TLS, certbot)
├── clinic.example      → /var/www/hmsv2/public      (web-public build)
├── app.clinic.example  → /var/www/hmsv2/staff       (web-staff build)
└── api.clinic.example  → 127.0.0.1:8000 (uvicorn, systemd)

PostgreSQL 16 (local socket): databases `hmsv2`, `hmsv2_audit`
/var/lib/hmsv2/uploads/                 (attachments)
/var/backups/hmsv2/                     (nightly dumps + uploads)
```

## 3. Step-by-step

### 3.1 VPS bootstrap (`deploy/scripts/bootstrap.sh`, Ubuntu 24.04)

1. Create user `hmsv2` (no sudo), dirs `/var/www/hmsv2/{public,staff}`, `/var/lib/hmsv2/uploads`, `/var/backups/hmsv2`.
2. `apt install postgresql-16 nginx certbot python3.12-venv libmagic1 clamav clamav-daemon age` + `ufw allow 80,443` (deny rest). Start/update the ClamAV daemon before enabling uploads.
3. Postgres: `createuser hmsv2` + `createdb hmsv2 -O hmsv2` + `createdb hmsv2_audit -O hmsv2`; audit DB: application role may execute only the append procedure and SELECT verification views. Revoke direct UPDATE/DELETE on `audit_event`, `audit_meta`, and checkpoints. The migration owner is separate and never used by the running API.
4. Backend: clone repo to `/opt/hmsv2`, `python3.12 -m venv .venv`, install, production `.env` (0600, from password manager): `APP_ENV=prod`, real `SECRET_KEY`, `DATABASE_URL=postgresql+psycopg://hmsv2:***@/hmsv2`, audit URL, SMTP, CORS origins = the three prod hosts only.
   Store a separate `FIELD_ENCRYPTION_KEY` for encrypted national-ID fields;
   keep it outside the database and document rotation/re-encryption before
   launch.
5. Run both alembic upgrades + seed (then change admin password immediately).
6. `deploy/systemd/hmsv2-api.service`: `uvicorn app.main:app --workers 1 --host 127.0.0.1 --port 8000`, `User=hmsv2`, `Restart=always`, `EnvironmentFile=/opt/hmsv2/.env`, hardening flags (`NoNewPrivileges`, `ProtectSystem=full`, `ReadWritePaths=/var/lib/hmsv2/uploads`, `ReadWritePaths=/var/lib/hmsv2/checkpoints`). One worker is deliberate because the v1 SSE broadcaster is in-process; scaling is a post-v1 Redis/pub-sub decision.
7. Build frontends locally (or on VPS): `npm ci && npm run build` in each app with prod env (`VITE_API_URL=https://api.clinic.example`, `VITE_PUBLIC_API_URL` same); `rsync dist/` to `/var/www/hmsv2/*`.
8. nginx: three server blocks from `deploy/nginx/`; certbot `--nginx` for all three; verify A+ basics (HSTS after first week).
9. Backups (§4) + logrotate + cron.
10. `deploy/scripts/deploy.sh` (repeatable): pull → venv sync → both alembic upgrades → build frontends → rsync → `systemctl restart hmsv2-api` → health check → done. Prints rollback hint (git checkout previous tag + restart).

### 3.2 nginx specifics

- `client_max_body_size 20m` (uploads) on api only; rejected oversized requests are logged without request bodies.
- SSE routes: `proxy_buffering off; proxy_cache off; proxy_read_timeout 3600s;` for `/api/queue/stream`, `/api/notifications/stream`, `/api/chat/stream`.
- Security headers on all: `X-Content-Type-Options nosniff`, `X-Frame-Options DENY`, `Referrer-Policy strict-origin-when-cross-origin`, CSP for the two sites (`default-src 'self'`; `connect-src 'self' https://api.clinic.example`; `img-src 'self' data: https://api.clinic.example`; fonts only from approved self/data sources), API served with `Content-Type` JSON only.
- Refresh cookies: `HttpOnly`, `Secure`, `SameSite=Lax` (or `None` only when a documented cross-site deployment requires it), narrow `Domain`/`Path`, and explicit logout revocation. CSRF token required for cookie-authenticated mutations.
- Static sites: `try_files $uri /index.html` (SPA), immutable cache for `/assets/*` (hashed), no-cache for `index.html`.
- Clinical/API responses and authenticated file downloads send `Cache-Control: private, no-store`; only `/api/public/assets/*` and versioned static assets may be publicly cached.
- gzip on; brotli if available.
- Rate limit zones at nginx level too (belt & braces): 10 r/s per IP on `/api/public/`, burst 20.

### 3.3 Backend hardening

- slowapi: public API per-IP limits (booking 10/h, register 5/h, chat per Plan/08 C5, global 60/min).
- CORS: exact staff/public origins only, `allow_credentials=true` solely for
  the refresh/CSRF cookie flow, and no wildcard origin/method/header settings.
- Security middleware: request size cap 20MB; trusted-host check.
- `pg_trgm` index on `patient_profile(full_name)` + `phone` for search speed.
- Install and configure ClamAV for production attachment scanning; if the scanner is unavailable, attachment uploads fail closed rather than becoming downloadable.
- Encrypt the VPS volume or upload/backups at rest, restrict `/var/lib/hmsv2/uploads` to the service user, and never expose it through nginx.
- Structured logs (JSON lines) → journald; `logrotate` not needed with journald; set `SystemMaxUse=500M`.
- The single API process runs the persisted outbox worker for email and
  attachment scans. It claims jobs with a `lease_until` lease, retries with backoff, and
  resumes pending/processing jobs after restart; no email or scan work exists
  only in volatile memory.
- Admin force-password-change on first login (flag from seed).
- Password reset, role change, and suspected compromise revoke every active
  refresh-token family for that user. Add an admin "revoke all sessions" action.
- Audit events are never deleted or compacted in v1. Signed checkpoints and
  encrypted exports are the archive strategy; disk monitoring must alert before
  capacity becomes a safety incident.

## 4. Backups (`deploy/scripts/backup.sh`, cron nightly 03:30)

1. `pg_dump -Fc hmsv2` + `pg_dump -Fc hmsv2_audit` → encrypt with `age` using a public backup key, then store in `/var/backups/hmsv2/{date}/`.
2. `tar czf uploads-{date}.tgz /var/lib/hmsv2/uploads` → encrypt with the same off-server `age` recipient before it leaves the VPS.
3. Keep 14 daily + 4 weekly (rotate by date math).
4. `sha256sum` manifest per backup dir.
5. Export a signed audit checkpoint after each backup; copy the checkpoint and its signature to a separate location/account. A backup on the same VPS is not an independent audit anchor.
6. Copy encrypted backups and signed checkpoints to a second administrative
   location or offline medium; this is mandatory for the audit guarantee. `rsync`
   is one implementation if the owner provides an off-site destination.
7. **Restore drill (mandatory before launch):** fresh dir → `pg_restore` both DBs → point a dev instance at them → run audit verify + signature verification + unresolved-intent reconciliation → document timing in this file's execution notes.

## 5. Launch checklist

- [ ] All phase Done-when lists pass
- [ ] `pytest` + both `vitest` suites green on the release commit
- [ ] Audit chain verify: green on prod data after seed+smoke
- [ ] Signed audit checkpoint created and verified from a separate copy
- [ ] Audit application role cannot directly UPDATE/DELETE chain rows
- [ ] Unresolved audit intents = 0 after smoke and restore drill
- [ ] Restore drill done (§4.7) with recorded duration
- [ ] UFW: only 80/443/ssh; Postgres local-only; `.env` 0600
- [ ] Clinical files are not reachable through nginx/static URLs
- [ ] Service worker inspection confirms no clinical API caching
- [ ] TLS A/A+ (ssllabs), HSTS planned
- [ ] Public API rate limits verified with a burst test
- [ ] Backups ran 3 consecutive nights; manifest hashes match
- [ ] Outbox retry test: restart API while an email/scan job is pending; job resumes exactly once
- [ ] Admin password changed; demo doctor replaced with real data; demo appointments purged
- [ ] **Open compliance item (D17):** clinic accountant confirmed whether ETA e-Receipt is required; if yes → schedule the roadmap item before taking payments digitally
- [ ] Owner sign-off on: booking flow (AR), exam screen speed, cashier, board, prints

## 6. Operational runbook (short)

- **Restart API:** `systemctl restart hmsv2-api` (zero-downtime not required at clinic scale; do it after hours).
- **Logs:** `journalctl -u hmsv2-api -f`.
- **Audit verify weekly:** curl admin endpoint; alert if red or if unresolved intents > 0. Verify the latest signed checkpoint from the separate copy.
- **Disk watch:** uploads + backups on same volume — alert at 80% (simple cron `df` check emailing admin).
- **Audit retention:** never delete audit events to save space; alert at 70% and
  require an external archive expansion plan before reaching 80%.
- **Update flow:** `deploy.sh` from a tagged commit; rollback = previous tag.

## 7. Gotchas

- The in-process SSE broadcaster requires exactly one API worker in v1. If the clinic later needs more workers, introduce Redis/pub/sub before changing this unit.
- certbot renewal hook must `systemctl reload nginx`.
- `pg_dump` while live is fine; still schedule at 03:30.
- Never expose `*.clinic.example` phpMyAdmin-style DB tools — psql via SSH only.
