# HMSv2 — Master Plan

**Revision 2.0 — safety, state-machine, and deployment coherence pass**

Clinic management system for a **single clinic with a few doctors** in Egypt.
FastAPI backend · two React/Vite/TS frontends (staff app + separate public site) ·
SQLite dev / PostgreSQL prod · separate hash-chained audit DB · **no Docker anywhere** ·
Arabic + English (full RTL).

> This file is the master reference. Every build phase has its own extremely
> detailed file in `Plan/`. Read `Plan/00-Design-Language.md` before any UI work.

---

## 1. Documentation Index

| File | Phase | Contents |
|---|---|---|
| `Plan/00-Design-Language.md` | — | Brand, colors, typography, spacing, components, RTL, motion, print design. **Binding for all UI.** |
| `Plan/01-Scaffold.md` | 1 | Monorepo layout, tooling, dev scripts, two Alembic configs, both Vite apps |
| `Plan/02-Backend-Core.md` | 2 | Settings, dual DB engines, all core models, JWT auth + roles, hash-chained audit service |
| `Plan/03-Scheduling.md` | 3 | Doctor schedules, blocks, visit types, hybrid availability engine, appointments |
| `Plan/04-Queue-Waiting-Room.md` | 4 | Check-in, arrival queue, walk-ins, SSE waiting-room board, TV mode |
| `Plan/05-EMR.md` | 5 | Visit record (all-optional), attachments/PWA camera, drug DB, prescriptions, timeline, follow-ups |
| `Plan/06-Financial.md` | 6 | Price lists, syndicates/co-pay, auto-invoice, payments (EG methods, partial), discounts, reports |
| `Plan/07-Printables-Recall-Search.md` | 7 | Print templates (Rx/report/sick-leave/referral), recall list, no-show stats, ⌘K search |
| `Plan/08-Chat-Notifications.md` | 8 | Support chat (AI-ready), in-app notifications, email, wa.me reminder composer |
| `Plan/09-Staff-Frontend.md` | 9 | Every staff/doctor/admin screen, component inventory, UX specs |
| `Plan/10-PWA.md` | 10 | Installable app, camera capture, mobile doctor layout, performance budgets |
| `Plan/11-Public-Website.md` | 11 | Landing page, booking flow, patient account + family profiles, chat widget |
| `Plan/12-i18n.md` | 12 | AR/EN translation system, RTL, fonts, numerals, print locales, QA checklist |
| `Plan/13-Hardening.md` | 13 | Rate limits, backups, systemd, nginx, TLS, logging, launch checklist |

---

## 2. Confirmed Decisions (locked with the owner)

| # | Decision | Value |
|---|---|---|
| D1 | Scale | Single clinic, few doctors. No multi-tenancy. Multi-branch is post-v1 only. |
| D2 | Stack | FastAPI + SQLAlchemy 2.0 + Alembic · React 18 + Vite + TypeScript (both apps) |
| D3 | Databases | SQLite in dev, PostgreSQL in prod. **Audit log in a separate database**, hash-chained. |
| D4 | Containers | **None.** venv + systemd + nginx on a plain VPS. |
| D5 | Reverse proxy | nginx (certbot for TLS). |
| D6 | Mobile | PWA / responsive web app for doctors (camera capture). No native app. |
| D7 | Languages | Arabic + English, full RTL. Arabic-first. |
| D8 | Scheduling | **Hybrid per doctor**: exact time slots *or* day-booking + arrival queue. Walk-ins. Visit types (duration + price). Per-doctor shifts, capacity limits, blocked days, follow-up linking. |
| D9 | Patient self-service | Public site account: book / view / cancel / reschedule. **No medical data access.** No phone/email verification in v1. |
| D10 | Family profiles | One patient account manages multiple patient profiles (children, parents). Reception can create profiles with no account. |
| D11 | Doctor EMR | Full set, **every field optional**: complaint, history, vitals, clinical exam, findings, labs, imaging, diagnoses (DD + final), plan, notes-for-next-visit, prescriptions (**with drug DB**), attachments (photos of labs/imaging). Past visits = **timeline of cards showing non-null fields only**. |
| D12 | Financial | Per-visit or per-hour pricing per doctor. Syndicate/insurance contracts with patient co-pay + insurer balance tracking. Discounts by doctor/secretary (permission-capped). Invoices auto-generated on visit completion. Payments: cash/card/Fawry/InstaPay/wallet/Meeza; **partial payments/installments** supported. Reports: daily revenue, doctor share, syndicate balances. |
| D13 | Audit | Every mutating action and sensitive clinical-record access is recorded in a separate append-only audit DB. Events use an intent/commit protocol, hash chaining, immutable database permissions, and signed external checkpoints. This is tamper-evident and independently verifiable; no database design can honestly promise protection from a PostgreSQL superuser who can rewrite every storage layer. |
| D14 | Support chat | Public-site chat widget → secretary inbox. Schema AI-ready (`sender_type` includes future `ai`). **No AI in v1.** |
| D15 | Notifications | In-app (SSE bell) + email (SMTP, booking confirmations). **WhatsApp one-click reminders** via wa.me prefilled Arabic messages (per-patient + bulk). Automated WhatsApp is post-v1. |
| D16 | Egyptian market fit | EGP currency · phone-first identity · realtime waiting-room board · auto-invoice on visit completion · printables with clinic letterhead · recall list · no-show stats · ⌘K global patient search. |
| D17 | ETA e-Receipt | **Not built in v1.** Invoices designed to allow a future exporter (immutable once paid, per-year numbering). Flag as open compliance question for the clinic's accountant. |
| D18 | PDPL | Self-service export/erasure tooling **excluded from v1**. Audit log + role access control remain. Listed in post-v1 roadmap. |
| D19 | Verification | No SMS OTP / email verification in v1 (chosen by owner). Contact fields are explicitly marked unverified; reception confirms by phone when needed. |
| D20 | AI | Nothing AI in v1 (chat automation + SOAP summaries are post-v1; schema must not block them). |
| D21 | Clinical data safety | Clinical data is never exposed through public endpoints, browser service-worker caches, TV displays, email bodies, or patient account pages in v1. Offline staff mode is app-shell-only and read-only. |
| D22 | Write safety | Public bookings and all financial/clinical mutations accept idempotency keys. Clinical autosave uses optimistic record versions; silent last-write-wins is forbidden. |

---

## 3. Architecture

```
┌────────────────┐   HTTPS    ┌──────────────────────────────────────┐
│  web-public     │──────────▶ │  FastAPI backend                     │
│  (public site,  │  /api/public/* (rate-limited, CORS-locked)       │
│   own deploy)   │            │                                      │
└────────────────┘            │   /api/* (staff auth)                │
┌────────────────┐            │                                      │
│  web-staff      │──────────▶ │   Services: auth · audit · schedule  │
│  (staff PWA,    │            │   queue · emr · billing · chat ·     │
│   own deploy)   │            │   notify · search · print            │
└────────────────┘            └───────┬───────────────┬──────────────┘
                                      │               │
                               ┌──────▼─────┐  ┌──────▼──────┐   ┌──────────┐
                               │  main DB    │  │  audit DB    │   │ /uploads │
                               │ sqlite/pg   │  │ sqlite/pg    │   │  (disk)  │
                               └────────────┘  │ hash-chained │   └──────────┘
                                                └─────────────┘
```

- **Two API surfaces, one backend.** The public site only ever calls `/api/public/*` — it can be edited/redeployed/broken without touching staff operations. The API remains the only process allowed to read clinical files.
- **Deployables:** `backend` (systemd + uvicorn), `web-staff` (static build via nginx), `web-public` (static build via nginx, separate server block).
- **No Docker.** Dev: `scripts/dev.sh` starts venv uvicorn + two Vite dev servers. Prod: `deploy/` contains systemd units, nginx vhosts, backup cron scripts.

### Monorepo layout

```
HMSv2/
├── PLAN.md                  # this file
├── Plan/                    # per-phase detailed plans
├── backend/
│   ├── app/
│   │   ├── main.py          # app factory, middleware, routers
│   │   ├── core/            # config, security, constants, deps
│   │   ├── db/              # engines/sessions (main + audit), base
│   │   ├── models/          # SQLAlchemy models (main DB)
│   │   ├── audit/           # audit models (audit DB) + chain service
│   │   ├── schemas/         # Pydantic v2 schemas
│   │   ├── api/
│   │   │   ├── routes/      # staff API: /api/*
│   │   │   └── public/      # public API: /api/public/*
│   │   ├── services/        # availability, queue, billing, notify, search...
│   │   └── workers/         # persisted outbox: email + attachment scan jobs
│   ├── alembic/             # main DB migrations
│   ├── alembic_audit/       # audit DB migrations
│   ├── tests/
│   ├── requirements.txt
│   └── run.py               # dev entrypoint (exists)
├── web-staff/               # React+Vite+TS staff app (PWA in phase 10)
├── web-public/              # React+Vite+TS public site (separate deploy)
├── scripts/
│   └── dev.sh               # start everything locally
└── deploy/
    ├── systemd/  ├── nginx/  └── scripts/   # prod, no containers
```

### Ports & URLs

| App | Dev | Prod (placeholder) |
|---|---|---|
| backend | `http://localhost:8000` | `https://api.clinic.example` |
| web-staff | `http://localhost:5173` | `https://app.clinic.example` |
| web-public | `http://localhost:5174` | `https://clinic.example` |

### Conventions (binding)

- API prefix: staff `/api/…`, public `/api/public/…`. JSON everywhere. Errors: `{ "detail": { "code": "…", "message": "…" } }`. Resource mutations require an `Idempotency-Key` (login/refresh/logout are authentication commands and are exempt); replaying a completed key returns the original result.
- Times stored **UTC**; clinic timezone setting (default `Africa/Cairo`) governs "today", slots, queues.
- Money: `Numeric(12,2)`, currency from settings (default `EGP`). Never float.
- IDs: integer PKs. Human codes: patient `P-000001`, booking ref 8-char (`BK-3F9K2Q7A`), invoice `INV-2026-000001` (per-year sequence).
- Auth: short-lived JWT access tokens held in memory plus rotating refresh tokens in `HttpOnly`, `Secure`, `SameSite` cookies. Staff access 30m + refresh 30d. Patient access 30m + refresh 60d. Argon2id password hashing. Cookie mutations require a CSRF token.
- Every mutating endpoint goes through the **audit protocol** (see Plan/02). Sensitive EMR/attachment reads are also access-audited.
- Service workers cache only the app shell and non-sensitive public assets. They never cache patient, visit, invoice, attachment, auth, mutation, or SSE responses.
- Soft rules: staff can overbook with a warning; public booking never overbooks.

---

## 4. Roles & Permissions

| Capability | Admin | Doctor | Secretary | Patient (public) |
|---|---|---|---|---|
| Manage users/doctors/schedules/pricing | ✅ | own schedule/block requests | — | — |
| View audit log / export | ✅ | — | — | — |
| Settings & print templates | ✅ | — | — | — |
| All reports (revenue, doctor share, syndicate) | ✅ | own only | daily cashier only | — |
| Appointments: create/move/cancel | ✅ | own patients | ✅ | own only (book/cancel/reschedule) |
| Check-in / queue / walk-ins | ✅ | view own | ✅ | — |
| Waiting board "call next" | ✅ | ✅ | ✅ (reorder only) | — |
| EMR read/write | ✅ (read) | own write + shared-clinic read | demographics only; no clinical content | — |
| Prescription/clinical file content | ✅ (read) | own/shared clinical access | — | — |
| Prescriptions / printables | ✅ | ✅ | administrative print only; no clinical file download | — |
| Payments & discounts | ✅ | discount ≤ cap | payment + discount ≤ cap | — |
| Chat inbox reply | ✅ | — | ✅ | send from widget |
| Recall list | ✅ | view | ✅ | — |

Role guard: FastAPI dependency `require_role("admin" | "doctor" | "secretary")` (see Plan/02).

---

## 5. Data Model (summary — full column specs live in each phase file)

**Identity:** `staff_user`, `doctor` (profile + billing mode + slot config), `patient_account` (login) → many `patient_profile` (medical subject; `account_id` nullable so reception can create unattached profiles).

**Scheduling:** `visit_type` (duration + default price), `doctor_schedule` (weekly shifts), `schedule_block` (vacations/blocked), `appointment` (`booking_ref`, status machine `booked → checked_in → in_progress → completed | cancelled | no_show`, `follow_up_of_id` link), `queue_entry` (per doctor-day arrival sequence with `waiting → called → in_room → completed | left`).

**EMR:** `visit` (all-optional clinical fields + vitals JSON + follow-up), `visit_diagnosis` (differential|final, label, ICD-10 optional), `medication` (editable drug DB), `prescription` + `prescription_item`, `attachment` (labs/imaging photos).

**Financial:** `price_list_item` (per visit type, doctor override), `syndicate` + `syndicate_price` (`syndicate_coverage` + patient share), `invoice` (auto on visit completion; immutable once paid; per-year number) + `invoice_item` + `discount`, `payment` (method: cash/card/fawry/instapay/wallet/meeza; partial allowed).

**Comms/config:** `chat_conversation` + `chat_message` (`sender_type`: patient|secretary|system|ai-reserved), `notification` (in-app), `print_template`, `setting` (clinic info, caps, reminder text), `number_sequence`, `idempotency_key`.

**Public assets:** `public_asset` for doctor/clinic photos only; separate from patient attachments and publicly cacheable.

**Audit DB:** `audit_event` (actor, intent/commit outcome, action, entity, before/after JSON, IP, UA, correlation ID, `prev_hash`, `hash`) + `audit_checkpoint` (signed chain heads).

---

## 6. Key Flows (one-paragraph each; details in phase files)

1. **Public booking:** choose doctor → availability per doctor's mode (slots grid or day picker) → choose family member → confirm (no verification) → `booking_ref` shown + email confirmation. Staff see it instantly in calendar.
2. **Same-day reception:** waiting-room board (SSE). Check-in reserved patients → queue ordered by arrival. Walk-ins inserted with profile lookup/create. Exact-slot doctors still use the board for arrival reality.
3. **Exam (single screen):** doctor opens patient from queue → center: all-optional EMR form · left: timeline of past visits (non-null cards) · right: prescription builder + attachments + print actions. Doctor completes the visit → **invoice auto-created** → secretary collects payment. Saving a draft does not create a bill.
4. **Billing:** price resolved: syndicate contract → doctor override → visit-type default. Syndicate patient pays co-pay; remainder accrues to syndicate balance. Discounts within role caps. Partial payments until fully paid.
5. **Follow-up & recall:** doctor sets "follow up in N weeks" → `follow_up_due`. Recall list = due patients with no future booking → secretary one-click WhatsApp reminder.
6. **Chat:** widget on public site → conversation → secretary inbox (SSE). `sender_type=ai` reserved for post-v1 automation.
7. **Audit:** mutation intent is recorded before the main transaction, then committed/aborted outcome is recorded after it. A reconciliation job flags unresolved intents. Admin can browse/filter/export, verify the chain, and verify signed checkpoints.

---

## 7. Build Phases

Execute strictly in order; each phase file contains step-by-step tasks, UI specs, and acceptance criteria. A phase is done only when its **Done-when** checklist passes.

| # | Phase | File | Produces |
|---|---|---|---|
| 1 | Scaffold | `Plan/01-Scaffold.md` | Repo, tooling, both apps boot, migrations run |
| 2 | Backend core | `Plan/02-Backend-Core.md` | Models, auth, roles, audit protocol |
| 3 | Scheduling | `Plan/03-Scheduling.md` | Availability engine + appointment APIs |
| 4 | Queue & waiting room | `Plan/04-Queue-Waiting-Room.md` | Check-in, board, SSE, TV mode |
| 5 | EMR | `Plan/05-EMR.md` | Visits, attachments, drug DB, Rx, timeline |
| 6 | Financial | `Plan/06-Financial.md` | Pricing, syndicates, invoices, payments, reports |
| 7 | Printables, recall, search | `Plan/07-Printables-Recall-Search.md` | Print templates, recalls, ⌘K |
| 8 | Chat & notifications | `Plan/08-Chat-Notifications.md` | Chat, SSE bell, email, wa.me composer |
| 9 | Staff frontend | `Plan/09-Staff-Frontend.md` | Complete staff app |
| 10 | PWA | `Plan/10-PWA.md` | Install + camera + mobile doctor UX |
| 11 | Public website | `Plan/11-Public-Website.md` | Landing + booking + account + widget |
| 12 | i18n | `Plan/12-i18n.md` | AR/EN + RTL everywhere |
| 13 | Hardening | `Plan/13-Hardening.md` | Prod deploy, backups, security, launch |

---

## 8. Post-v1 Roadmap (architecture must not block)

- Automated WhatsApp reminders 48/24/2h (Meta Cloud API or WAHA)
- AI: support-chat automation, SOAP summary drafting, no-show prediction
- Online payments (Paymob) incl. booking deposits
- Expenses / petty cash / P&L module
- Inventory (consumables, reorder alerts)
- Specialty EMR widgets (dental chart, growth curves…)
- ETA e-Receipt exporter
- PDPL self-service (data export/erasure)
- Multi-branch

## 9. Risks / Open Questions

| Risk | Mitigation in plan |
|---|---|
| Clinic is legally required to issue ETA e-receipts | Invoice immutability + per-year numbering already; verify with accountant before launch (Plan/13 checklist) |
| WhatsApp one-click is manual | Bulk "remind all today" composer; automation on roadmap |
| Fake bookings (no verification) | Rate limiting on public API + no-show tracking + reception phone confirmation habit |
| Audit DB fills disk | No event deletion in v1; signed external archive, monitoring, and capacity expansion strategy in Plan/13 |
| Doctor adoption (speed) | Single exam screen, ⌘K, all-optional fields, PWA camera — core design goals, not afterthoughts |
| Cross-database audit consistency | Intent/commit events, unresolved-intent reconciliation, signed checkpoints, and a launch restore/verification drill (Plan/02 and Plan/13) |
| Sensitive data in browser/device | No clinical service-worker cache, no offline clinical mutations, short-lived access tokens, authenticated file endpoints, and device/session revocation |

## 10. Revision 2.0 Summary

- Replaced the unsafe cross-database "single transaction" implication with an
  explicit audit intent → main commit → committed/aborted protocol, unresolved-
  intent reconciliation, append-only database permissions, and signed external
  checkpoints.
- Replaced browser-persisted refresh tokens and clinical service-worker caches
  with memory-only access tokens, HttpOnly refresh cookies, CSRF protection, and
  app-shell-only offline behavior.
- Normalized queue state to `waiting → called → in_room → completed | left`;
  only a completed visit can complete its queue entry and appointment.
- Added idempotency keys to public bookings, queue actions, clinical writes,
  chat messages, recalls, and payments/refunds.
- Added optimistic record versions for clinical and financial edits; stale
  writes return a conflict instead of silently overwriting records.
- Separated public doctor/clinic assets from patient attachments; added MIME
  validation, PDF scanning, ClamAV quarantine, encrypted fields/backups, and
  explicit session revocation.
- Narrowed secretary access to demographics/operational metadata and clarified
  which clinical documents can be printed.
