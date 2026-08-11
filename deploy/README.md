# HMSv2 deployment (no Docker — Plan/13)

- `systemd/hmsv2-api.service` — single-worker API unit (SSE broadcaster is
  in-process; do NOT raise workers without a pub/sub plan).
- `nginx/*.conf` — three server blocks: public site, staff app, API.
  SSE routes are unbuffered; clinical files are never served statically.
- `scripts/bootstrap.sh` — fresh Ubuntu 24.04 VPS setup (packages, user,
  dirs, Postgres, ufw).
- `scripts/deploy.sh <tag>` — pull, migrate, build, rsync, restart, health.
- `scripts/backup.sh` — nightly encrypted dumps + uploads + signed audit
  checkpoint; requires an off-server age recipient.

Mandatory before go-live (full list in Plan/13 §5):
restore drill, audit chain verify, ETA e-Receipt confirmation, admin password
rotation, TLS via certbot.
