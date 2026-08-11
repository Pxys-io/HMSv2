# HMSv2

Clinic management system: FastAPI backend + two Vite frontends (staff app &
public site), dual databases (main + hash-chained audit), no Docker.

**Start here: [`PLAN.md`](PLAN.md)** — Revision 2.0 master plan with per-phase detail files
in [`Plan/`](Plan/) (design language, backend core, scheduling, queue, EMR,
financial, printables, chat, frontends, PWA, public site, i18n, hardening).

## Checks & dev

- `./scripts/check.sh` — full pipeline: backend lint + tests, both frontends
  (typecheck, lint, tests, build), then boots the API on a fresh seeded dev DB
  and runs the live end-to-end smoke test (`scripts/smoke.py`).
- `./scripts/check.sh --skip-live` — code checks only.
- `./scripts/dev.sh` — run backend + both frontends locally.
