# Phase 02 — Backend Core

**Revision 2.0:** this phase now defines the security boundary, optimistic
write versions, idempotency records, and an honest cross-database audit
protocol. The audit chain is tamper-evident, not a claim that a database
superuser is unable to rewrite storage.

**Goal:** all core data models (main DB), JWT auth with roles, and the
tamper-evident audit service (separate DB, hash-chained). After this phase every
later phase is "just" routes + services on a solid base.

**Depends on:** 01. **Blocks:** 03–08.

---

## 1. Deliverables

- Full model layer for identity, scheduling, EMR, financial, comms (tables created now; behavior in later phases)
- Auth: staff + patient JWT (access/refresh, rotation), Argon2id hashing, role guards
- Audit service: append-only writer, hash chain, verification, SQLAlchemy hooks
- Seed command: admin user, default settings, demo doctor
- Base API plumbing: error format, pagination, request-id

## 2. Data model — full column specs (main DB)

Conventions: `id` = Integer PK. `created_at`/`updated_at` = UTC
`DateTime(timezone=True)` on all tables via `TimestampMixin`. Money = `Numeric(12,2)`.

### 2.1 Identity

**`staff_user`** — internal users (all roles)

| column | type | notes |
|---|---|---|
| email | String(255) unique, lower-cased | login |
| password_hash | String(255) | Argon2id |
| full_name | String(200) | |
| full_name_ar | String(200) nullable | |
| phone | String(32) nullable | |
| role | Enum: `admin`, `doctor`, `secretary` | index |
| is_active | Bool default true | |
| last_login_at | DateTime nullable | |

**`doctor`** — 1:1 with staff_user where role=doctor

| column | type | notes |
|---|---|---|
| staff_user_id | FK staff_user unique | |
| specialty | String(120) | free text v1 |
| title | String(120) nullable | e.g. "Consultant" |
| bio / bio_ar | Text nullable | public site |
| public_asset_id | FK public_asset nullable | public doctor photo; never a patient attachment |
| booking_mode | Enum: `slots`, `day_queue` | **hybrid per doctor** |
| default_slot_minutes | Int default 20 | slots mode |
| buffer_minutes | Int default 0 | gap between slots |
| day_capacity | Int nullable | max bookings/day (null = unlimited) |
| slot_capacity | Int default 1 | parallel bookings per slot |
| billing_mode | Enum: `per_visit`, `per_hour` | |
| hourly_rate | Numeric(12,2) nullable | required iff per_hour |
| is_bookable_online | Bool default true | |

**`patient_account`** — public-site login

| column | type | notes |
|---|---|---|
| email | String(255) unique nullable | email OR phone required (CHECK) |
| email_verified_at | DateTime nullable | always null in v1 unless verified later |
| phone | String(32) unique nullable | normalized digits |
| phone_verified_at | DateTime nullable | always null in v1 unless verified later |
| password_hash | String(255) | |
| full_name | String(200) | account owner |
| locale | Enum `ar`,`en` default `ar` | |
| is_active | Bool default true | |
| last_login_at | DateTime nullable | |

**`patient_profile`** — the medical subject (appointments/visits attach here)

| column | type | notes |
|---|---|---|
| code | String(12) unique | `P-000001` from number_sequence |
| account_id | FK patient_account **nullable** | null = reception-created |
| full_name | String(200) | |
| full_name_ar | String(200) nullable | |
| gender | Enum `male`,`female`,`other`,`unknown`,`prefer_not_to_say` nullable | never force a value |
| birth_date | Date nullable | age computed |
| phone | String(32) | contact phone |
| phone_alt | String(32) nullable | |
| national_id_ciphertext | LargeBinary nullable | encrypted at application level; never searchable or returned in full |
| address | String(300) nullable | |
| allergies | Text nullable | alert in exam strip |
| chronic_conditions | Text nullable | alert in exam strip |
| notes | Text nullable | reception notes |
| no_show_count | Int default 0 | denormalized |
| is_archived | Bool default false | no hard delete after clinical history exists |
| record_version | Int default 1 | optimistic concurrency |
| syndicate_id | FK syndicate nullable | default insurer |
| syndicate_member_no | String(64) nullable | |

**`number_sequence`** — human codes: `scope` String(40), `year` Int nullable,
`value` Int, unique(scope, year). Atomic `UPDATE … RETURNING` increment.

### 2.2 Scheduling

**`visit_type`**: `name` String(120), `name_ar` String(120), `duration_minutes`
Int default 20, `default_price` Numeric(12,2), `color` String(7) nullable,
`is_active` Bool.

**`doctor_schedule`**: `doctor_id` FK, `weekday` SmallInt 0–6 (Mon=0),
`start_time` Time, `end_time` Time, `effective_from`/`effective_to` Date
nullable, `is_active` Bool. Overlapping rows allowed (union of intervals).

**`schedule_block`**: `doctor_id` FK, `date_from` Date, `date_to` Date,
`reason` String(200) nullable.

**`appointment`**

| column | type | notes |
|---|---|---|
| booking_ref | String(12) unique | `BK-XXXXXXXX` |
| patient_profile_id | FK | |
| doctor_id | FK | |
| visit_type_id | FK | |
| date | Date | clinic-local, index |
| start_time | Time nullable | null in `day_queue` mode |
| end_time | Time nullable | computed for slots |
| status | Enum: `booked`,`checked_in`,`in_progress`,`completed`,`cancelled`,`no_show` | index |
| source | Enum: `public`,`staff`,`walk_in` | |
| follow_up_of_id | FK appointment nullable | follow-up link |
| cancel_reason | String(300) nullable | |
| cancelled_by | String(40) nullable | `patient:<id>` / `staff:<id>` |
| reminder_link_generated_at | DateTime nullable | manual wa.me link generation tracked; does not imply delivery |
| booked_by_staff_id | FK staff_user nullable | |

Service-enforced guard (slots mode): no overlapping active appointments beyond
`slot_capacity` for same doctor/date/time.

### 2.3 Queue

**`queue_entry`**

| column | type | notes |
|---|---|---|
| doctor_id | FK | |
| date | Date | clinic-local; composite index (doctor_id, date) |
| seq | Int | arrival order per (doctor_id, date) |
| appointment_id | FK appointment nullable | null for pure walk-ins |
| patient_profile_id | FK | always set |
| visit_type_id | FK nullable | walk-in declares type |
| status | Enum: `waiting`,`called`,`in_room`,`completed`,`left` | `completed` only after visit completion |
| checked_in_at | DateTime | |
| called_at | DateTime nullable | TV display trigger |
| started_at / ended_at | DateTime nullable | operational timing; visit timing is billing source of truth |

### 2.4 EMR

**`visit`**

| column | type | notes |
|---|---|---|
| patient_profile_id | FK | index |
| doctor_id | FK | |
| appointment_id | FK nullable | |
| queue_entry_id | FK nullable | |
| visit_type_id | FK | |
| started_at / ended_at | DateTime nullable | ended drives per-hour fee |
| chief_complaint | Text nullable | |
| history | Text nullable | |
| vitals | JSON nullable | `{bp, hr, temp_c, weight_kg, height_cm, spo2}` — all optional |
| clinical_exam | Text nullable | |
| findings | Text nullable | |
| labs | Text nullable | |
| imaging | Text nullable | |
| plan | Text nullable | |
| notes_next_visit | Text nullable | surfaced in timeline + next-exam banner |
| notes_private | Text nullable | doctor-only, never printed |
| follow_up_weeks | Int nullable | |
| follow_up_due | Date nullable | index (recalls) |
| status | Enum: `open`,`completed` | |
| record_version | Int default 1 | required on every PATCH; conflict → 409 |
| last_saved_by | FK staff_user nullable | |

**`visit_diagnosis`**: `visit_id` FK, `kind` Enum `differential`,`final`, `label` String(300), `icd10_code` String(16) nullable, `notes` String(300) nullable, `order` SmallInt.

**`medication`** (editable drug DB): `name` String(200), `name_ar` String(200) nullable, `form` String(60) (tab/syrup/amp…), `strength` String(60), `default_dose`/`default_frequency`/`default_duration` String nullable, `is_active` Bool. Unique(name, form, strength).

**`prescription`**: `visit_id` FK unique (one Rx per visit in v1), `notes` Text nullable, `issued_by` FK staff_user.

**`prescription_item`**: `prescription_id` FK, `medication_id` FK nullable (null = free-text drug), `free_text` String(300) nullable, `dose` String(120), `frequency` String(120), `duration` String(60), `instructions` String(300) nullable, `quantity` String(60) nullable, `order` SmallInt.

**`attachment`**

| column | type | notes |
|---|---|---|
| patient_profile_id | FK | |
| visit_id | FK nullable | may attach to profile directly |
| kind | Enum: `lab`,`imaging`,`report`,`photo`,`other` | |
| title | String(200) nullable | |
| file_path | String(500) | relative to UPLOAD_DIR |
| thumb_path | String(500) nullable | images only |
| mime | String(100) | |
| size_bytes | Int | |
| uploaded_by_type | Enum `staff` | patient upload reserved for post-v1 |
| uploaded_by_id | Int | |
| scan_status | Enum `pending`,`clean`,`rejected` | file is not downloadable until clean |
| sha256 | String(64) | duplicate detection and integrity check |

### 2.5 Financial

**`price_list_item`**: `visit_type_id` FK, `doctor_id` FK nullable (null = clinic default), `price` Numeric(12,2), unique(visit_type_id, doctor_id).

**`syndicate`**: `name` String(200), `name_ar` nullable, `code` String(40) unique, `contact_phone`/`contact_email` nullable, `notes` Text nullable, `is_active` Bool.

**`syndicate_price`**: `syndicate_id` FK, `visit_type_id` FK, `doctor_id` FK nullable, `syndicate_coverage` Numeric(12,2) (the amount billed to the syndicate), `patient_share` Numeric(12,2) default 0, unique(syndicate_id, visit_type_id, doctor_id). The service total is coverage + patient share; the names intentionally remove the old contract-price ambiguity.

**`invoice`**

| column | type | notes |
|---|---|---|
| number | String(20) unique | `INV-2026-000001` |
| patient_profile_id | FK | |
| visit_id | FK nullable unique | auto-created from visit |
| appointment_id | FK nullable | |
| doctor_id | FK | |
| syndicate_id | FK nullable | |
| subtotal | Numeric(12,2) | |
| discount_total | Numeric(12,2) default 0 | |
| total | Numeric(12,2) | |
| patient_due | Numeric(12,2) | total − syndicate covers |
| syndicate_due | Numeric(12,2) default 0 | |
| paid_total | Numeric(12,2) default 0 | service-maintained |
| refunded_total | Numeric(12,2) default 0 | positive aggregate of refund rows |
| currency | String(3) default `EGP` | snapshotted at issue |
| record_version | Int default 1 | financial mutation lock/version |
| status | Enum: `issued`,`partially_paid`,`paid`,`refunded`,`cancelled` | |
| issued_by | FK staff_user | |
| issued_at | DateTime | |

Immutable after first payment (service-enforced; corrections = refund/credit note).

**`invoice_item`**: `invoice_id` FK, `description` String(300), `description_ar` nullable, `qty` Numeric(8,2) default 1, `unit_price` Numeric(12,2), `line_total` Numeric(12,2), `visit_type_id` FK nullable.

**`discount`**: `invoice_id` FK, `kind` Enum `percent`,`fixed`, `value` Numeric(8,2), `reason` String(300) nullable, `granted_by` FK staff_user. Role-cap checked in service.

**`payment`**: `invoice_id` FK, `amount` Numeric(12,2) positive, `method` Enum `cash`,`card`,`fawry`,`instapay`,`wallet`,`meeza`, `reference` String(120) nullable, `received_by` FK staff_user, `paid_at` DateTime default now, `is_refund` Bool default false. Refunds are positive rows and are subtracted in net calculations; never store negative payments.

### 2.6 Comms & config

**`chat_conversation`**: `patient_account_id` FK nullable (guest chat: then `guest_name`, `guest_contact` strings), `guest_key_hash` String(64) nullable, `status` Enum `open`,`closed`, `subject` String(200) nullable (auto from first message), `assigned_to` FK staff_user nullable, `last_message_at` DateTime, `unread_staff` Int default 0, `unread_patient` Int default 0.

**`chat_message`**: `conversation_id` FK, `sender_type` Enum `patient`,`secretary`,`system`,`ai` (**ai reserved, never used in v1**), `sender_id` Int nullable, `body` Text, `created_at` indexed, `read_at` nullable.

**`notification`**: `staff_user_id` FK, `type` String(40) (`chat_new`,`booking_new`,`booking_cancelled`,`payment_due`…), `title` String(200), `body` String(500) nullable, `link` String(300) nullable, `read_at` nullable, `created_at` indexed.

**`print_template`**: `key` String(40) (`rx`,`report`,`sick_leave`,`referral`,`invoice`), `locale` Enum `ar`,`en`, `title` String(120), `body_html` Text (allowlisted placeholders only), `is_active` Bool, `sanitized_at` DateTime, unique(key, locale). Scripts, event handlers, external URLs, and arbitrary CSS are rejected.

**`setting`**: `key` String(80) unique, `value` JSON. Known keys: `clinic.name`, `clinic.name_ar`, `clinic.address`, `clinic.phones`, `clinic.country_code` (default `20`), `clinic.hours_text`, `clinic.hours_text_ar`, `clinic.location_url`, `clinic.timezone` (default `Africa/Cairo`), `clinic.public_asset_id`, `billing.currency`, `billing.discount_cap_secretary_pct` (default 10), `booking.horizon_days` (default 30), `reminder.whatsapp_template_ar`, `reminder.whatsapp_template_en`, `public.about`, `public.about_ar`, `public.services`, `public.services_ar`.

**`idempotency_key`**: `owner_type`, `owner_id` nullable, `key` String(120), `request_hash` String(64), `status` Enum `processing`,`succeeded`,`failed`, `response_status` Int nullable, `response_json` JSON nullable, `expires_at`, unique(owner_type, owner_id, key). Never reuse a key with a different request hash.

**`outbox_event`**: `id`, `kind` Enum `email_booking_confirmation`,`attachment_scan`, `aggregate_type`, `aggregate_id`, `payload` JSON, `status` Enum `pending`,`processing`,`sent`,`failed`, `attempts`, `next_attempt_at`, `lease_until`, `worker_id`, `last_error`, `dedupe_key` unique. It makes email and scanning restart-safe; a small in-process worker drains it in v1.

**`public_asset`**: `id`, `kind` Enum `clinic_logo`,`doctor_photo`,`public_image`, `file_path`, `mime`, `size_bytes`, `sha256`, `is_active`, `created_at`. Images are re-encoded and EXIF-stripped before public serving. No patient or clinical foreign keys.

### 2.7 Audit DB (separate base `AuditBase`)

**`audit_event`**

| column | type | notes |
|---|---|---|
| id | BigInt PK | |
| occurred_at | DateTime UTC default now, index | |
| actor_type | Enum `staff`,`patient`,`system` | |
| actor_id | Int nullable | |
| actor_label | String(200) | snapshot name/email |
| action | String(60) index | e.g. `appointment.create`, `payment.add`, `auth.login` |
| entity_type | String(60) index nullable | |
| entity_id | String(60) nullable | string to fit codes |
| correlation_id | String(36) index | joins intent/commit/abort events |
| outcome | Enum `intent`,`committed`,`aborted`,`access` | immutable event meaning |
| before_json | JSON nullable | |
| after_json | JSON nullable | |
| context_json | JSON nullable | extras (request-id…) |
| ip | String(64) nullable | |
| user_agent | String(300) nullable | |
| prev_hash | String(64) | hex sha256; genesis = 64 zeros |
| hash | String(64) unique | sha256(prev_hash ‖ canonical_json(row-without-hash)) |

**`audit_meta`** — single row: `genesis_hash`, `last_hash`, `last_id`, `created_at`. O(1) append.

**`audit_checkpoint`** — `id`, `created_at`, `first_event_id`, `last_event_id`,
`chain_head_hash`, `signature`, `public_key_id`, `export_path`. A daily or
manual checkpoint is signed with an Ed25519 private key stored outside both
databases. The public key is kept in the repository/deployment config and in a
second backup location.

## 3. Auth design

- Passwords: Argon2id via `pwdlib`. Constant-time errors ("Invalid credentials" for unknown user & bad password alike).
- Tokens (PyJWT): access JWTs are held in memory only. **Staff** access = 30m,
  claims `{sub, typ:"staff", role, name}`; **patient** access = 30m,
  `{sub, typ:"patient"}`. Refresh tokens are opaque random values stored only
  as hashes and sent in `HttpOnly`, `Secure`, `SameSite` cookies; staff expiry
  30d, patient expiry 60d, with rotation.
- **`refresh_token`** (main DB): `id`, `owner_type` Enum staff/patient, `owner_id` Int, `token_hash` String(64) unique, `family_id`, `expires_at`, `revoked_at` nullable, `created_by_ip`, `created_at`. Logout = revoke. Reuse of a rotated token → revoke the entire family.
- Cookie-authenticated mutations require a double-submit or synchronizer CSRF
  token (`X-CSRF-Token`); CORS never substitutes for CSRF protection.
- Staff SSE clients use `fetch()` with an `Authorization: Bearer` header and a
  streaming reader; do not put access tokens in query strings because native
  `EventSource` cannot set headers. The public chat widget uses authenticated
  `fetch` polling, and the TV uses its separately rotatable display token.
- Deps: `get_current_staff`, `get_current_patient`, `require_role(*roles)` (403 `FORBIDDEN`), `get_optional_patient` (guest chat).
- Login lockout: 10 failed attempts / account / 10 min → 429 (in-memory counter OK for single-process v1).

### Auth endpoints

| Method & path | Body | Returns |
|---|---|---|
| POST `/api/auth/login` | email, password | `{access_token, user}` + refresh cookie |
| POST `/api/auth/refresh` | cookie | new access token + rotated cookie |
| POST `/api/auth/logout` | cookie | 204 + cookie revocation |
| GET `/api/auth/me` | — | staff user (+doctor profile if any) |
| POST `/api/public/auth/register` | full_name, email?, phone?, password + `Idempotency-Key` | account + access token + refresh cookie |
| POST `/api/public/auth/login` | email_or_phone, password | tokens |
| POST `/api/public/auth/refresh`, `/logout`, GET `/me` | — | — |

### Admin user/doctor management

`GET/POST /api/users`, `PATCH /api/users/{id}` (role, active, reset password),
`GET/POST /api/doctors`, `PATCH /api/doctors/{id}` (all doctor config incl.
booking_mode, billing). Resource writes require `Idempotency-Key`; schedule
CRUD is wired in phase 03.

Public-asset contract: `POST /api/public-assets` (admin; logo/doctor photo only,
separate scan/size limits), `GET /api/public/assets/{id}` (public-safe read),
and `PATCH /api/doctors/{id}` may attach an existing public asset. Public asset
URLs never point at `/api/files/{attachment_id}`.

## 4. Audit service (`backend/app/audit/`)

1. **Writer** `audit.log(audit_db, *, actor, action, outcome, correlation_id, entity=None, before=None, after=None, ctx=None, request=None)`:
   - canonicalize payload JSON (sorted keys, UTF-8, compact separators)
   - row-lock `audit_meta` → `prev_hash` = last_hash or 64 zeros
   - `hash = sha256(prev_hash + canonical)`; insert through a stored procedure or append-only DB role; update chain head; commit on the audit session only.
2. **Cross-database protocol:** before a mutating main-DB transaction, append an
   `intent` event with a correlation ID and proposed before/after values. Commit
   the main transaction only after the intent succeeds. After main commit,
   append `committed`; on rollback append `aborted`. If the process dies between
   these steps, a reconciliation command compares unresolved intents with the
   main DB and records the result. This avoids falsely claiming a completed
   action while acknowledging that two independent databases cannot provide
   atomic two-phase commit by magic.
3. **Failure policy:** if the intent cannot be written, the main mutation does
   not start. If the final outcome event cannot be written, the system raises a
   high-priority operational alert and leaves an unresolved intent for
   reconciliation; it never silently drops the gap. Read-only endpoints do not
   create mutation events, but sensitive EMR/file reads create `access` events.
4. **Capture points:** explicit service calls for business actions (login
   success/fail, check-in, payment, discount, cancel…) and access events for
   clinical records. Do not rely on generic SQLAlchemy hooks alone for action
   names; use hooks only to catch unexpected writes and fail tests.
5. **Verifier** `audit.verify()` walks the chain ordered by id and verifies
   hashes, outcomes, unresolved intents, and signed checkpoints → `{ok,
   broken_at_id?, unresolved_count, checked}`. Exposed at
   `POST /api/audit/verify` (admin).
6. **Viewer API (admin):** `GET /api/audit/events` (filters: date range, actor,
   action prefix, entity, outcome; paginated), `GET /api/audit/events/{id}`,
   `GET /api/audit/export?from&to` → NDJSON download, and
   `POST /api/audit/reconcile`.
7. `X-Request-ID` (uuid) middleware on every request; stored as
   `correlation_id` and in `context_json`.

## 5. Plumbing

- **Errors:** raise `AppError(code, message, status)` → `{detail:{code,message}}`. Common codes: `VALIDATION`, `UNAUTHORIZED`, `FORBIDDEN`, `NOT_FOUND`, `CONFLICT`, `RATE_LIMITED`.
- **Pagination:** `page` (1-based), `page_size` (default 20, max 100) → `{items, total, page, page_size}`.
- **Schemas:** Pydantic v2 in `app/schemas/`, one module per domain, `from_attributes=True`.
- **Seed** `python -m app.seed`: development-only demo data. Production seed
  creates no known password; it requires `INITIAL_ADMIN_PASSWORD` or prints a
  one-time random bootstrap secret to the terminal and marks the account for
  immediate password change. Never commit or document a production password.
- **Sensitive fields:** national ID is encrypted at application level and is
  never included in list/search responses. Patient profiles with visits are
  archived, not deleted. Contact verification timestamps remain null in v1.

## 6. Step-by-step tasks

1. Mixins + conventions (`db/base.py`); models split across `models/{identity,scheduling,queueing,emr,billing,comms,config}.py`.
2. Alembic autogenerate → review → upgrade (main). Audit models → separate migration → upgrade (audit).
3. `core/security.py` (hash/verify, JWT, refresh issue/rotate/revoke + family revocation).
4. `core/deps.py` (get_db, get_audit_db, auth deps, role guard).
5. `core/errors.py`, middleware (request-id, timing), exception handlers.
6. Audit service + append-only role/procedure + meta bootstrap (genesis) + signed checkpoint key handling + unit tests (chain verify, tamper, unresolved-intent reconciliation).
7. Auth routes (staff + public) + users/doctors admin CRUD.
8. Seed command + smoke script: login → me → logout.
9. Tests (§8).

## 7. UI/UX in this phase

None (API only). Frontend auth flows are specified in Plan/09 & 11 and must match these exact endpoints/shapes.

## 8. Tests (pytest, tmp SQLite files)

- Register/login/me/refresh/logout happy paths; wrong password; inactive user 403; role guard denies (secretary → admin route).
- Refresh rotation: old token reuse → 401 + family revoked.
- Patient register requires email OR phone; duplicate → 409 `CONFLICT`.
- Profile code sequence: two profiles → `P-000001`, `P-000002`.
- Audit: create user via API → one `user.create` intent plus one committed outcome sharing a correlation ID; verify ok; **tamper test**: flip a byte in `after_json` via raw SQL → verify returns `broken_at_id`.
- Audit failure path: audit engine pointed at invalid URL → mutating request → 500 (documented behavior).
- Idempotency: same key + same request returns the first response; same key + different request hash → 409; expired keys are rejected/cleaned.
- Clinical PATCH with stale `record_version` → 409 with server copy, never silent overwrite.
- Access audit: doctor opens a shared visit and downloads an attachment → two `access` events; secretary metadata-only access does not expose file bytes.
- Public asset endpoint contains no patient/visit foreign key and is cacheable; clinical file endpoint is authenticated and non-cacheable.

## 9. Done-when checklist

- [ ] All main-DB §2 tables exist in the main database and all audit-DB tables exist in the audit database; one Alembic head per environment
- [ ] Seed runs; admin logs in; role guards behave per PLAN.md §4
- [ ] Every mutation follows intent → main commit → committed/aborted audit flow; unresolved-intent reconciliation is tested
- [ ] Tamper test detects modification
- [ ] Signed checkpoint creation and public-key verification work after an audit export/restore
- [ ] Error/pagination shapes match §5 on every route
- [ ] `pytest` green; `ruff` clean

## 10. Gotchas

- Never pretend main-DB and audit-DB sessions share a transaction. Use the intent/commit protocol in §4.2 and expose unresolved intents instead of hiding them.
- JSON canonicalization must be stable (sorted keys, compact separators) or verification false-positives.
- SQLite + `Numeric`: fine via SQLAlchemy; still round money to 2dp in service layer.
- Keep `patient_profile.phone` denormalized from account — families share one account phone but grandma's profile has her own.
- Do not use browser localStorage for refresh tokens, clinical data, or guest chat credentials; use HttpOnly cookies for refresh and hashed opaque guest keys server-side.
- SQLite development cannot enforce PostgreSQL role permissions; emulate the
  append-only audit boundary in tests and treat PostgreSQL permissions/triggers
  as a production launch gate.
