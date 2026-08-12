# Phase 14 — ERP Round 2 (Flexibility, Finance, Ops/CRM, EMR depth, Inventory, HR)

**Revision 1.0 — scope locked with the owner (build this, nothing else).**

**Goal:** turn the clinic HMS into a *fully flexible, easy ERP*: configurable
roles & custom fields, VAT + expenses + petty cash + P&L, a KPI dashboard,
per-patient activity stream & communication log, tags, tasks, referrals, lab
orders, duplicate detection + merge + unarchive, bulk actions, patient-accessible
documents, automated *local* reminders, deeper EMR (ICD-10 picker, structured
labs + trends, vitals reference ranges, growth charts), a complete
inventory/pharmacy module, and HR (attendance, leaves, payroll).

**Explicitly OUT of scope (next plan):** bulk SMS, WhatsApp/email automation,
kiosk check-in, bulk CSV import, drug-allergy interaction warnings,
consent/waiver e-signature capture, online payments, multi-branch, PDPL
self-service tooling.

---

## 0. Delivery order & dependencies

| Step | Block | Depends on |
|---|---|---|
| A1 | Custom roles/permissions | — (refactor touches every route → do first) |
| A2 | Custom fields | A1 |
| A3 | VAT/tax in finance | A1 |
| B | Expenses + petty cash + P&L | A3 |
| C1 | Dashboard + KPIs | A1, B |
| C2 | Activity stream service + hooks | A1 |
| C3 | Communication log + hooks | A1, A3 (emailer, reminders) |
| C4 | Patient tags/segments | A1 |
| C5 | Internal tasks | A1 |
| C6 | Referral tracking | A1 |
| C7 | Lab-order tracking | A1 |
| C8 | Duplicate detection + merge + unarchive | A1, C2 (merge logs activity) |
| C9 | Bulk actions | A1, C3, C4 |
| C10 | Patient-accessible docs (public) | A1, printing service |
| C11 | Automated local reminders | A1, C3 |
| D1 | ICD-10 autocomplete | A1 |
| D2 | Structured labs + trends | A1 |
| D3 | Vitals reference ranges | A1 |
| D4 | Growth charts | A1 |
| E | Inventory & pharmacy | A1, D2 (dispensing links Rx) |
| F | HR — attendance, leaves, payroll | A1 |
| G | Frontend integration (staff + public) | A1–F |

Each step is code-complete before the next starts; `./scripts/check.sh` must be
green at the end of A1 and after every subsequent step's test additions.

---

## A1. Custom roles & permissions

### Goal
Replace the hard-coded 3-role enum with a data-driven permission matrix.
Existing behavior unchanged by default (the 3 system roles get exactly today's
capabilities), but admins can create roles, edit permission sets, and assign
them to staff. The `PLAN.md` role table becomes the *default seed*, not the law.

### Data model (new tables in main DB)

```
role            id PK, name uniq, name_ar, is_system bool, is_active bool
permission      id PK, code uniq, label, label_ar, group (e.g. "billing")
role_permission role_id FK, permission_id FK, uq(role_id, permission_id)
```

`staff_user` changes: **drop** `role` enum column; **add** `role_id` FK NOT
NULL. Backfill = create the 3 system roles (`admin`, `doctor`, `secretary`)
with today's full permission sets, map every existing user by their old enum
value. Old column removed in the same migration.

### Permission codes (complete matrix)

Group `patient`: `patient.view`, `patient.edit`, `patient.merge`, `patient.archive`
Group `appointment`: `appointment.view`, `appointment.create`, `appointment.edit`,
`appointment.cancel`, `appointment.no_show`
Group `queue`: `queue.view`, `queue.checkin`, `queue.call`, `queue.start`,
`queue.complete`, `queue.move`, `queue.close_day`
Group `emr`: `emr.view`, `emr.write`, `emr.prescribe`, `emr.attach`, `emr.labs`
Group `billing`: `billing.view`, `billing.invoice`, `billing.discount`,
`billing.payment`, `billing.refund`, `billing.manage_pricing`, `billing.expense`
Group `inventory`: `inventory.view`, `inventory.edit`, `inventory.purchase`,
`inventory.dispense`
Group `hr`: `hr.attendance`, `hr.leave`, `hr.payroll`
Group `ops`: `ops.task`, `ops.dashboard`, `ops.activity_view`, `ops.tag`,
`ops.referral`, `ops.lab_order`, `ops.communication`, `ops.duplicates`
Group `chat`: `chat.view`, `chat.reply`
Group `report`: `report.all`, `report.own`, `report.cashier`
Group `admin`: `admin.users`, `admin.roles`, `admin.settings`, `admin.audit`,
`admin.custom_fields`, `admin.templates`, `admin.schedule_manage`

**Seed defaults (system roles):**
- **admin:** every permission.
- **doctor:** `patient.view/edit`, `appointment.view/create/edit` (own), `queue.view/call/start/complete` (own), `emr.*`, `billing.view/discount`, `inventory.view/dispense`, `ops.task/dashboard/referral/lab_order/activity_view`, `chat.view`, `report.own`, `hr.attendance` (own clock).
- **secretary:** `patient.view/edit`, `appointment.*` except none, `queue.*` except `queue.move`→actually today secretary may reorder → keep `queue.move`, `billing.view/invoice/payment/expense` + `billing.discount` (cap-limited), `inventory.view`, `ops.*`, `chat.view/reply`, `report.cashier`, `hr.attendance` (own clock).

Dr. share-of-revenue etc. remain business rules in code; permissions gate *who may hit the endpoint*, not amounts.

### API

| Method & path | Purpose |
|---|---|
| `GET /api/roles` · `POST /api/roles` · `PATCH /api/roles/{id}` | list / create / edit custom roles (system roles read-only except permissions) |
| `GET /api/permissions` | permission catalog (grouped) |
| `GET /api/roles/{id}/permissions` · `PUT /api/roles/{id}/permissions` | view / replace permission set |
| `PATCH /api/users/{id}/role` | assign role (admin only) |

All under `admin.roles` / `admin.users`. Idempotency keys on mutations.

### Backend changes
- `app/core/deps.py`: new `require_perm(*codes)` dependency reading
  `current.role.permissions` (cached on request); keep `require_role("admin")`
  as a thin wrapper checking `role.is_system and role.name == "admin"` (and
  `"doctor"`/`"secretary"` similarly) so the phase-2 guards still work.
- Replace the ~40 `require_role(...)` usages with the equivalent permission
  guards per the matrix above. **No behavioral change for system roles.**
- `PATCH /api/users/{id}` gains `role_id` (admin).
- Seed inserts roles + full matrix in `app/seed.py`; tests assert seed parity.

### Frontend
- Admin page: new **Roles** tab → role list, permission checkbox matrix grouped
  by module, role create/edit, staff tab shows role selector.
- Auth store keeps `role` for UI switches (board vs today) — derive from
  `role.is_system ? role.name : "custom"` + `permissions[]` array used by a
  small `Can perm="..."` component; hide nav items without permission.

### Done-when
- Login as each system role behaves identically to pre-refactor (full regression).
- Admin can create role "cashier" with only `billing.view/payment/expense` and
  a staff user with it sees only cashier nav and is 403 on `/api/patients`.
- `check.sh` green.

---

## A2. Custom fields (patients + visits)

### Goal
Admins define extra data fields for patient profiles and visits, rendered
dynamically in the forms, validated server-side. Zero-code configurability.

### Data model
```
custom_field  id PK, entity enum(patient, visit), key uniq per entity (snake_case),
              label, label_ar, type enum(text, textarea, number, date, select,
              multiselect, boolean), options JSON (for select/multiselect),
              is_required bool, is_active bool, order int
```
Values are stored **inline on the entity as JSON** (no EAV table — clinic scale
is tiny, simpler and fast): `patient_profile.custom_data JSON`, `visit.custom_data JSON`.

### Rules (binding)
- **F1:** key auto-generated from label (transliterated + uniquified); cannot change after creation.
- **F2:** server validates on every PATCH: unknown keys rejected, required present, type-coerced, select/multiselect values ∈ options.
- **F3:** custom fields never participate in pricing, search ranking (v1), or the audit `before/after` JSON beyond the whole entity snapshot already captured.
- **F4:** deactivating a field hides it from forms and keeps old values readable; deleting a field is **forbidden** if any row has a value (must deactivate).

### API
| Method & path | Purpose |
|---|---|
| `GET /api/custom-fields?entity=` · `POST /api/custom-fields` | admin CRUD (admin.custom_fields) |
| `PATCH /api/custom-fields/{id}` · `POST /api/custom-fields/{id}/deactivate` | edit / deactivate |
| `GET /api/custom-fields/schema?entity=` | full schema incl. options (staff only) |

Patient PATCH and visit PATCH accept `custom_data` object; payloads return it.

### Frontend
- Admin → Custom Fields tab: entity toggle, field list, add/edit form (label EN/AR, type, options editor, required, order).
- Patient form + Exam form: render dynamic inputs from schema (select/multiselect chips, date, number, toggle); `custom_data` persisted with normal save.

### Done-when
- Admin adds a patient field "Blood group" (select) and a visit field "Smoker" (boolean); both render and round-trip with validation (missing required → 422; bogus option → 422).
- Deactivated field disappears from forms, old value still returned in payloads.

---

## A3. VAT / tax handling

### Goal
Clinic configures a tax rate (Egypt standard 14%, medical often exempt → default **0%**), invoices snapshot the rate, totals split into subtotal / discount / tax / total, printed & CSV-exported. Works inclusive or exclusive.

### Settings (new keys)
- `billing.vat_rate_pct` (Numeric, default `0`)
- `billing.vat_inclusive` (bool, default `true` — prices entered include tax)
- `billing.vat_number` (str, default `""` — tax ID printed on invoice)
- `billing.vat_exempt` (bool, default `false` — clinic-wide exemption; printed "VAT-exempt")

### Rules (binding)
- **V1 — Snapshot:** invoice creation copies `vat_rate_pct`, `vat_inclusive`,
  `vat_number`, `vat_exempt` onto the invoice. Later settings changes never
  touch existing invoices (matches M5 immutability).
- **V2 — Math:** `subtotal` = sum of item `line_total` (pre-tax). `discount_total` applied to subtotal (same M3 rules). Taxable = `subtotal − discount_total`.
  - exclusive: `tax_total = taxable × rate/100`; `total = taxable + tax_total`.
  - inclusive: prices already include VAT → `tax_total = taxable × rate/(100+rate)`; `total = taxable` (tax shown as "of which VAT").
- **V3 — Items:** each `invoice_item` gets `tax_rate` (nullable, defaults to invoice rate at creation). Manual items can set a different rate or 0.
- **V4 — Payments/refunds** always operate on `total` (VAT never separately payable). Refund of a full invoice returns gross incl. VAT; tax recomputed proportionally if partial refund → not needed: refunds are amounts, VAT attribution only in reports.
- **V5 — Reports:** daily-revenue, doctor-share, P&L include `tax_total` column; CSV same. ETA-e-receipt flag: invoice print footer shows VAT split + `vat_number` when `vat_rate_pct > 0`.

### Data model
`invoice`: add `tax_rate Numeric(5,2)`, `tax_total Numeric(12,2) default 0`,
`vat_inclusive bool`, `vat_number str(64)`, `vat_exempt bool`.
`invoice_item`: add `tax_rate Numeric(5,2) nullable`.

### API / endpoints
No new endpoints; invoice payload, print template, and reports gain the new
fields. Settings tab edits the 4 keys.

### Frontend
- Cashier invoice drawer: shows subtotal / discount / VAT / total; "incl. VAT" hint; per-item rate badge.
- Invoice print (existing template) gains tax block.
- Settings tab: VAT fields.

### Done-when
- Invoice with rate 14% inclusive: total == sum of gross prices; tax_total == total×14/114; printed VAT block correct.
- Rate change after invoice creation does not mutate the invoice; CSV reports include tax_total.

---

## B. Expenses + petty cash + P&L

### Goal
Record clinic spending, run a petty-cash fund ledger, and produce a P&L
(revenue − expenses) report. This is the biggest missing finance piece.

### Data model
```
expense  id PK, expense_number uniq (EXP-YYYY-NNNNN), category enum(rent,
         utilities, salaries, medical_supplies, marketing, maintenance,
         taxes, other), category_other str(120)?, description str(300),
         amount Numeric(12,2), tax_rate Numeric(5,2) default 0,
         tax_amount Numeric(12,2) default 0, fund_source enum(main, petty_cash),
         payment_method (reuse payment method enum) nullable,
         paid_at DateTime, paid_by staff FK, notes Text?,
         receipt_attachment_id? (reuse attachment? → v1: no file; link optional later)
         record_version int default 1

petty_cash_transaction  id PK, kind enum(top_up, expense_paid, withdraw,
                        refund_to_main), amount Numeric(12,2), note str(200)?,
                        created_by staff FK, created_at DateTime
```

### Rules (binding)
- **E1:** `petty_cash_balance = Σ(top_up + refund_to_main) − Σ(expense_paid + withdraw)`. Never stored; always derived. A `withdraw`/`expense_paid` exceeding balance → 409 `INSUFFICIENT_FUNDS`.
- **E2:** creating an expense with `fund_source=petty_cash` writes both the expense row and a `petty_cash_transaction(kind=expense_paid)` in the same transaction. `fund_source` immutable after creation.
- **E3:** expenses are soft-editable (description/notes) until month end; amount/category edits after that → require admin (audited). No hard delete; cancel = `cancelled` status? → v1: **no cancellation**, corrections via new expense + note (keep ledger simple); flagged for next plan.
- **E4 — P&L:** `net = Σ payments(receipts) − Σ refunds − Σ expenses` per period; grouped by month; rows: revenue by method, expenses by category, monthly net; CSV export. Permission `report.all` (admin), `billing.expense` for expense entry.

### API
| Method & path | Purpose |
|---|---|
| `GET /api/expenses?from&to&category&fund_source` | list (billing.view) |
| `POST /api/expenses` | create (billing.expense) + Idempotency-Key |
| `PATCH /api/expenses/{id}` | edit pre-month-end (billing.expense) |
| `GET /api/petty-cash` | ledger + derived balance |
| `POST /api/petty-cash/top-up` · `POST /api/petty-cash/withdraw` | fund ops (admin) |
| `GET /api/reports/pl?from&to&format=csv` | P&L (report.all) |

### Frontend
- Cashier page: "Expenses" tab → list + quick-add modal (category, amount, fund source, method); "Petty cash" panel with balance + ledger + top-up/withdraw (admin).
- Reports page: P&L card (revenue, expenses, net) + monthly breakdown + CSV.

### Done-when
- Expense logged → P&L reflects it; petty cash balance matches ledger; over-withdraw blocked with 409; check.sh green.

---

## C. Ops & CRM (C1–C11)

### C1. Dashboard + KPIs
- `GET /api/dashboard/summary` (permission `ops.dashboard`; role-scoped):
  - **Admin/secretary:** today's appointments (booked/checked-in), queue waiting (all doctors), invoices: collected today / outstanding, expenses today, no-shows today, new patients today, visits completed today, reminders due (next 24h), low-stock count (inventory.view), tasks due (all open, mine first), open chat conversations.
  - **Doctor:** own queue, own appointments today, own completed visits, own reminders due, own tasks.
- Frontend: new `DashboardPage` at `/` replacing the blind redirect: KPI cards + "due today" lists (reminders, tasks, invoices to collect). Per-role composition; nav highlights.

### C2. Activity stream
```
activity_event  id PK, patient_profile_id FK idx, actor_id staff FK,
                actor_role str(20)?, action str(60) (e.g. visit.created,
                appointment.cancelled, payment.added, patient.merged), 
                entity str(40), entity_id int?, detail JSON?, created_at
```
- Service helper `log_activity(db, profile_id, actor, action, entity, entity_id, detail)` called from: visit create/complete/reopen, appointment book/move/cancel/no-show, check-in, walk-in, invoice create/payment/refund/discount, prescription save, attachment upload/delete, patient create/merge/archive/unarchive, tag change, lab order create/status, reminder auto-sent, task create/close (linked to profile).
- `GET /api/patients/{id}/activity?limit&offset` (`ops.activity_view`). UI: patient detail "Activity" tab (icon + localized label + relative time). Explicitly *not* the audit DB — user-facing feed, no hash chain.

### C3. Communication log
```
communication  id PK, patient_profile_id FK idx, appointment_id?, invoice_id?,
               channel enum(email, whatsapp, sms, inapp, call, manual),
               direction enum(out, in), subject str(200)?, body str(500)?
               (truncated), ref str(120)? (email id / wa.me target),
               status str(40)? (sent, delivered, opened, draft),
               sent_at DateTime, created_by staff FK?
```
- Write hooks: emailer confirmation enqueue → status `sent` on actual send (outbox worker); wa.me reminder-link generation → `whatsapp` `draft` (manual send); automated local reminder (C11) → `inapp`; staff manual entry `POST /api/patients/{id}/communications`.
- `GET /api/patients/{id}/communications` + `GET /api/communications?from&to&channel` (ops.communication).
- UI: patient detail "Contact" tab timeline; Report page filter.

### C4. Tags / segments
```
tag  id PK, name uniq, color str(7)
patient_tag  patient_profile_id FK, tag_id FK, uq(pair)
```
- `GET/POST /api/tags` · `PATCH /api/tags/{id}`; `GET /api/patients/{id}/tags`, `PUT /api/patients/{id}/tags` (replace set); `GET /api/patients?tag_id=` filter in list.
- UI: chip editor on patient detail; tag filter dropdown on Patients page.

### C5. Internal tasks
```
task  id PK, subject str(200), notes Text?, assignee_id staff FK?, creator_id staff FK,
      priority enum(low, medium, high) default medium, due_date Date?,
      status enum(open, done, cancelled) default open,
      patient_profile_id? FK, appointment_id? FK,
      completed_at?, completed_by? FK
```
- Full CRUD + `GET /api/tasks?assignee=me|all&status&due`, `POST /api/tasks/{id}/complete` / `/reopen` (ops.task).
- UI: Tasks tab on Dashboard (due today), Tasks page (nav) with filters, quick "New task" from patient detail.

### C6. Referrals
```
referral  id PK, patient_profile_id FK idx, referred_by str(120) (name),
          specialty str(80)?, contact_phone str(32)?, clinic str(120)?,
          notes Text?, referred_at Date default today, created_by staff FK
```
- CRUD `GET/POST /api/patients/{id}/referrals`, `PATCH /api/referrals/{id}`; report `GET /api/reports/referrals?from&to` (per referring doctor counts) (ops.referral).
- UI: patient detail "Referrals" tab + Reports entry.

### C7. Lab-order tracking
```
lab_order  id PK, patient_profile_id FK idx, visit_id? FK, lab_name str(120),
           priority enum(routine, urgent) default routine,
           status enum(ordered, sampled, sent, results_received, cancelled)
           default ordered, ordered_by staff FK, ordered_at DateTime,
           results_received_at DateTime?, notes Text?
lab_order_item  id PK, lab_order_id FK, test_name str(120),
                status enum(pending, done) default pending,
                result_value str(80)?, unit str(20)?, reference str(60)?
```
- `POST /api/lab-orders` (from visit or patient), `PATCH /api/lab-orders/{id}/status`, `PUT /api/lab-orders/{id}/results` (items w/ values), `GET /api/patients/{id}/lab-orders`, `GET /api/lab-orders?status=open` (ops.lab_order).
- UI: Exam page "Labs" section (create order, mark sent, enter results) + patient detail tab showing history. Links to D2 structured results when received.

### C8. Duplicate detection + merge + unarchive
- **Detection:** `GET /api/patients/duplicates` (admin; `patient.merge`) — candidate pairs scored: (a) same normalized phone, (b) same `national_id` ciphertext, (c) same birth_date + name similarity ≥ 0.85 (difflib ratio on normalized AR/EN names). Score = 1.0 exact / weighted; returns `{pairs: [{a_id, b_id, a_name, b_name, score, reasons[]}]}`.
- **Merge:** `POST /api/patients/{keep_id}/merge/{drop_id}` + Idempotency-Key (admin): transactional reassign of every child row (visits, appointments, invoices, attachments, lab_orders, growth, communications, tasks, referrals, queue entries — queue only if same doctor-day & still waiting, else left) to `keep`; union tags; keep's syndicate unless null → adopt drop's; keep demographics untouched; write `patient.merged` activity on keep + full audit event; `drop` gets **hard-deleted** after verification count check (nothing left referencing it). No financial renumbering (invoices keep their numbers).
- **Unarchive:** `POST /api/patients/{id}/unarchive` (patient.edit) — flips `is_archived`, activity event. UI: Patients list gets "Archived" filter → Restore button.

### C9. Bulk actions (no bulk SMS)
- `POST /api/appointments/bulk-check-in` `{appointment_ids: []}` + Idempotency-Key (queue.checkin): checks in all valid; returns per-id results; skips non-booked with reason.
- `POST /api/patients/bulk-tag` `{profile_ids: [], tag_ids: []}` (ops.tag): adds tags to all.
- `POST /api/communications/bulk` `{profile_ids: [], channel: "whatsapp", subject, body}` (ops.communication): creates manual outbound log rows + returns prefilled `wa.me` links per profile phone (bulk *composer*, not bulk *send* — sends stay manual one-by-one; links are for the secretary's phone).
- UI: Calendar "select day" → bulk check-in button; Patients list multi-select → tag + compose reminder links.

### C10. Patient-accessible documents (public site)
- **Scope decision (binding):** invoices/receipts only. Per D21, prescription/clinical content is **not** exposed on the patient account — a flagged open question for the owner, noted in this plan.
- Backend: `GET /api/public/documents` (own invoices, paid/partially_paid, non-cancelled) + `GET /api/public/documents/invoices/{id}/pdf` → renders the existing invoice print template (stripped of internal notes; shows clinic letterhead, items, VAT block, totals, status) as PDF, patient-owned only (401 otherwise).
- Frontend (web-public): Account page "Documents" tab → invoice list + download buttons.

### C11. Automated local reminders (in-app only)
- `appointment` gains `reminder_sent_at DateTime?`, `reminder_stage int default 0`.
- Settings: `reminder.stages_hours` (list of int, default `[24, 2]`).
- Worker `services/reminders.py::auto_tick(db)` — runs from the app-lifespan task loop (like the outbox loop), every 15 min: for each booked appointment whose stage `n < len(stages)` and `start − now ≤ stages[n]` and not yet reminded at that stage → (1) `reminder_stage = n+1`, `reminder_sent_at = now`; (2) create staff notification (secretaries + admins) "Reminder due: Patient (booking BK-…)" — *staff-facing* because there is no patient in-app surface yet; (3) write `communication(channel=inapp, direction=out)` row; (4) activity event. No email, no WhatsApp (per owner: email+WhatsApp later).
- `GET /api/reminders/today` already exists (manual wa.me) — unchanged.
- UI: Dashboard "Reminders due (24h)" list with one-click wa.me (existing composer).

### Done-when (all of C)
- Every C endpoint tested; activity shows for a full patient lifecycle; duplicate pair found for two profiles sharing phone → merge moves all rows and drops the loser; bulk check-in handles mixed validity; public invoice PDF downloads only for the owning account; auto_tick advances stages once each and logs to communication + activity.

---

## D. EMR depth (D1–D4)

### D1. ICD-10 autocomplete
- Bundle a curated ICD-10 subset as a static JSON asset (`backend/app/data/icd10_common.json`, ~300 codes covering primary-care/Egypt-common: A00–A99 infections, E00–E90 endocrine, I00–I99 cardio, J00–J99 resp, K00–K93 GI, M00–M99 musculo, N00–N99 urogenital, R00–R99 symptoms, Z00–Z99 factors). Seed import optional — serve read-only from the asset.
- `GET /api/icd10?q=` (emr.view): prefix search on code + label (EN/AR), top 25. 
- Frontend: diagnosis row gets a typeahead (code + label); picking sets `label` + `icd10_code`; typing free text allowed (label only, no code).

### D2. Structured labs + trends
```
lab_test_result  id PK, patient_profile_id FK idx, visit_id? FK, test_name str(120),
                 value Numeric(14,4)?, unit str(20)?, reference_min Numeric(12,2)?,
                 reference_max Numeric(12,2)?, flag enum(normal, high, low)? (derived),
                 result_at Date default today, entered_by staff FK, note str(200)?
```
- CRUD: `POST /api/visits/{id}/lab-results` (bulk list), `PATCH /api/lab-results/{id}`, `GET /api/patients/{id}/lab-results?test_name=` (series for trend), delete (emr.labs).
- Derived flag: value < min → low; > max → high; computed server-side, stored.
- Frontend: Exam "Labs" tab table (existing free-text `labs` stays as prose); patient detail "Labs" tab shows history grouped by test with a tiny SVG sparkline (hand-rolled, no chart lib) when ≥ 3 points.

### D3. Vitals reference ranges
```
vitals_range  id PK, key str(40) (bp_systolic, bp_diastolic, heart_rate,
              temperature, respiratory_rate, spo2, glucose, bmi), 
              age_min_years int?, age_max_years int?, sex enum? nullable,
              min Numeric(8,2)?, max Numeric(8,2)?, is_active bool default true
```
- Seed defaults: adult BP 90–120/60–80, HR 60–100, temp 36.1–37.2 °C, RR 12–20, SpO2 95–100, fasting glucose 70–99, BMI 18.5–25; pediatric HR/temp rows; admin CRUD (`admin.settings`).
- Service `classify_vitals(vitals_json, profile)` → per-key `{value, unit, flag: normal|high|low|missing, range: {min, max}}`; matched by key + age/sex.
- API: `GET /api/vitals-ranges` + admin CRUD; visit payload returns classified vitals.
- Frontend: Exam vitals editor flags out-of-range values (red/amber chip) live; tooltip shows range.

### D4. Growth charts (pediatric)
- `growth_measurement` id PK, patient_profile_id FK idx, measured_on Date, height_cm Numeric(5,1)?, weight_kg Numeric(5,1)?, head_cm Numeric(4,1)?, bmi Numeric(5,1)?, entered_by staff FK.
- WHO percentile data bundled as static JSON (`backend/app/data/who_growth.json`): boys/girls × (weight-for-age, height-for-age) × age 0–60 months × curves P3/P15/P50/P85/P97. (Simplified table: P3/P50/P97 only if size is a concern — decide at build; aim full 5 curves, ~5 KB per series.)
- API: `GET/POST /api/patients/{id}/growth`, `PATCH /api/growth/{id}`, `DELETE` (emr.labs/write); `GET /api/growth/percentiles?sex=&metric=wfa|hfa` serves the bundled table (public-safe static data).
- Frontend: patient detail "Growth" tab → SVG chart (age × value) plotting the 3–5 percentile curves + patient points; add/edit form. Metric toggle + WHO table download note.

### Done-when (all of D)
- ICD picker returns bundled codes; lab results flag high/low and render a trend line; vitals entry of BP 160/95 flags red for an adult and normal for a documented hypertensive child-range row; growth chart plots real measurements against percentiles.

---

## E. Inventory & pharmacy

### Goal
Products, stock ledger, suppliers, purchases (PO → receive), batches with
expiry, dispensing from prescriptions, low-stock + expiring alerts, inventory
value report.

### Data model
```
product            id PK, name uniq, name_ar?, category str(80),
                   unit str(20) (tablet, ampule, bottle, box, ...),
                   buy_price Numeric(12,2) default 0, sell_price Numeric(12,2) default 0,
                   min_stock Numeric(12,2) default 0, stock_qty Numeric(12,2) default 0
                   (running total), sku?, barcode?, is_active bool, notes Text?

stock_movement     id PK, product_id FK idx, kind enum(purchase_in, dispense_out,
                   adjust_in, adjust_out, damaged_out, return_in),
                   qty Numeric(12,2) (signed), prev_qty, new_qty,
                   ref_type str(30)?, ref_id int?, note str(200)?,
                   created_by staff FK, created_at DateTime

supplier           id PK, name uniq, contact_person?, phone?, email?, notes?, is_active

purchase           id PK, number uniq (PO-YYYY-NNNNN), supplier_id FK,
                   status enum(draft, received, cancelled), total Numeric(12,2),
                   received_at?, notes?, created_by FK
purchase_item      id PK, purchase_id FK, product_id FK, qty Numeric(12,2),
                   unit_cost Numeric(12,2), line_total Numeric(12,2)

product_batch      id PK, product_id FK, batch_no str(80)?, expiry_date Date?,
                   qty_remaining Numeric(12,2), purchase_item_id FK?
                   (for FIFO receipt)

dispensing         id PK, prescription_item_id FK idx, product_id FK, qty Numeric(12,2),
                   batch_id FK?, dispensed_by staff FK, dispensed_at DateTime, note?
```
`prescription_item` gains nullable `product_id FK`.

### Rules (binding)
- **I1 — Stock is a ledger.** Only `stock_movement` rows change `stock_qty`; every insert updates `stock_qty` in the same transaction (row lock) and stores `prev_qty`/`new_qty`. Manual adjustments are `adjust_in/out` with a required note.
- **I2 — FIFO/expiry-first dispensing.** `POST /api/dispensing` decrements batches ordered by `expiry_date ASC NULLS LAST`, never below zero (409 `INSUFFICIENT_STOCK` with available qty). Optionally links `prescription_item.product_id` so the exam screen can prefill.
- **I3 — Purchases.** Draft PO edits freely; `receive` (idempotency key) → status `received`, one `purchase_in` movement per item, batches created per item (`expiry_date` optional at item level → `product_batch`), `stock_qty += qty`. Cancel only while draft.
- **I4 — Alerts:** `stock_qty <= min_stock` → `GET /api/inventory/alerts` low-stock list; batches expiring ≤ 30 days → expiring list. Dashboard shows counts (dashboard + inventory.view).
- **I5 — Damages/returns** are movements with notes; never hard-delete a movement.
- **I6 — Permissions:** view/edit (secretary, admin), purchase (admin), dispense (doctor, admin). Selling price used only for the inventory-value report (v1 has no POS).
- **I7 — Inventory value report:** per product: qty × buy_price (cost), qty × sell_price (retail), totals + CSV (`report.all`).

### API
| Method & path | Purpose |
|---|---|
| `GET/POST /api/products` · `PATCH /api/products/{id}` · `POST /api/products/{id}/adjust` | CRUD + stock adjustment (inventory.edit) |
| `GET/POST /api/suppliers` · `PATCH /api/suppliers/{id}` | suppliers |
| `GET/POST /api/purchases` · `PATCH /api/purchases/{id}` · `POST /api/purchases/{id}/receive` · `POST /api/purchases/{id}/cancel` | PO flow (inventory.purchase) |
| `GET /api/products/{id}/movements` · `GET /api/movements?from&to` | ledger |
| `POST /api/dispensing` | dispense (inventory.dispense) + Idempotency-Key |
| `GET /api/inventory/alerts` | low stock + expiring |
| `GET /api/reports/inventory-value?format=csv` | value report (report.all) |

### Frontend
- New nav **Inventory**: Products tab (table, adjust-stock modal, low-stock badge), Purchases tab (PO create → receive), Suppliers tab, Movements tab (filterable), Alerts panel.
- Exam page Rx tab: per line "Dispense" → product picker (search, shows stock), qty → success shows batch; decrement visible immediately.
- Dashboard: low-stock + expiring counts.

### Done-when
- Purchase received → stock up + batches with expiry; dispense drains oldest-expiry batch first; over-dispense → 409; alert lists low stock and ≤30d expiry; value report sums correctly; check.sh green.

---

## F. HR — attendance, leaves, payroll

### Data model
`staff_user` gains: `base_salary Numeric(12,2) default 0`, `hire_date Date?`,
`employment_type enum(full_time, part_time) default full_time`.

```
attendance      id PK, staff_user_id FK idx, work_date Date, clock_in Time?,
                clock_out Time?, status enum(present, late, leave, absent)
                default present, note str(200)?

leave_request   id PK, staff_user_id FK, leave_type enum(annual, sick, unpaid,
                other), from_date Date, to_date Date, days int,
                status enum(pending, approved, rejected, cancelled) default pending,
                reason Text?, decided_by staff FK?, decided_at DateTime?

payroll_period  id PK, year int, month int, uq(year, month),
                status enum(open, closed) default open, closed_by?, closed_at?
payroll_entry   id PK, period_id FK, staff_user_id FK,
                base_salary Numeric(12,2), days_worked Numeric(4,1),
                allowances Numeric(12,2) default 0, deductions Numeric(12,2) default 0,
                net Numeric(12,2), status enum(draft, paid) default draft,
                paid_at?, paid_by?, notes?
```

### Rules (binding)
- **H1 — Attendance:** staff clock in/out themselves (`hr.attendance`); admin can edit any record / add late/leave/absent rows (`hr.attendance` + admin). Late = clock_in after clinic-open setting (`clinic.open_time`, default 09:00). Absent = weekdays without a row (report-time derivation, not stored).
- **H2 — Leave:** requests by staff (`hr.leave`), approval by admin. `days` computed inclusive of both dates minus clinic weekend (Friday/Saturday default — setting `clinic.weekend_days` default `[4, 5]`). Approved leave auto-marks `attendance(status=leave)` for the range.
- **H3 — Payroll:** admin opens a period → entries auto-drafted for active staff (`days_worked` = weekdays in month − unpaid leave days − unapproved absences; formula documented, editable). Admin edits allowances/deductions, marks **paid** (locked after). Closing the period blocks edits; reopening allowed only by admin with audit.
- **H4 — Net:** `net = base_salary × days_worked/working_days − deductions + allowances`, where `working_days` = weekdays in period. Negative net → 422.
- **H5 — Reports:** monthly attendance summary (present/late/absent/leave per staff), payroll summary per period, monthly staff cost (`report.all`).

### API
| Method & path | Purpose |
|---|---|
| `POST /api/attendance/clock-in` · `POST /api/attendance/clock-out` | self (hr.attendance) |
| `GET /api/attendance?from&to&staff_user_id` | list |
| `POST /api/attendance` · `PATCH /api/attendance/{id}` | admin edit / add |
| `GET/POST /api/leaves` · `POST /api/leaves/{id}/approve|reject|cancel` | leave flow (hr.leave) |
| `GET /api/payroll/periods` · `POST /api/payroll/periods` (open) · `POST /api/payroll/periods/{id}/close|reopen` | periods (admin) |
| `GET /api/payroll/periods/{id}/entries` · `PATCH /api/payroll/entries/{id}` · `POST /api/payroll/entries/{id}/pay` | entries (admin) |
| `GET /api/reports/attendance?month=` · `GET /api/reports/payroll?period=` | reports |

### Frontend
- New nav **HR**: Attendance tab (today's clock + monthly grid), Leaves tab (requests, approve/reject), Payroll tab (period selector, entries table, pay/close).
- Staff tab (admin): salary/hire/type fields; profile menu: "Clock in/out".

### Done-when
- Clock-in at 09:30 flags late; approved leave marks attendance rows; payroll drafts with correct `days_worked`; pay locks entry; close locks period; check.sh green.

---

## G. Frontend integration summary

### web-staff
- **App.tsx routes:** `/` → Dashboard (role-composed); `/inventory`, `/hr`, `/tasks`; admin tabs **Roles**, **Custom Fields**; settings tab VAT fields; Reports gains P&L/Expenses/Referrals/Inventory-value.
- **PatientDetailPage tabs:** Demographics · Activity · Contact (communications) · Labs · Growth · Referrals · Tasks · Tags (inline chips on header).
- **ExamPage:** vitals flags; ICD typeahead; Labs tab (structured results + lab orders); Rx "Dispense" integration.
- **PatientsPage:** duplicate banner (admin), multi-select bulk actions, archived filter + Restore.
- **Cashier:** VAT breakdown; Expenses + Petty cash panel.
- Nav items gated by `Can` component (A1).
- i18n: all new strings AR/EN.

### web-public
- Account page: Documents tab (invoice list + PDF download, C10).

---

## H. Tests & migration strategy

- One Alembic revision per step group (A1 roles/perms + custom fields + VAT; B expenses/petty cash; C1–C11 tables; D1–D4; E inventory; F HR) — 6 revisions, applied via existing dual-alembic setup (main DB only; audit unchanged except nothing new).
- `app/seed.py` extended: system roles + permission matrix, default vitals ranges, bundled ICD-10 (from asset), WHO growth JSON (asset, not DB).
- New test files: `test_roles.py`, `test_custom_fields.py`, `test_vat.py`, `test_expenses.py`, `test_dashboard.py`, `test_activity.py`, `test_communications.py`, `test_tags.py`, `test_tasks.py`, `test_referrals.py`, `test_lab_orders.py`, `test_duplicates.py`, `test_bulk.py`, `test_public_documents.py`, `test_reminders_auto.py`, `test_icd10.py`, `test_lab_results.py`, `test_vitals_ranges.py`, `test_growth.py`, `test_inventory.py`, `test_hr.py`.
- `scripts/check.sh` extended to run the new suite (it already runs `backend/tests`).

---

## I. Open questions for the owner (non-blocking)

1. **Patient Rx download** — excluded (D21). Allow later? (Needs PDPL + explicit consent flow.)
2. **Expense cancellation** — v1 has no cancel; corrections create a new expense. OK?
3. **Payroll formula** — `base_salary × (days_worked/working_days) − deductions + allowances`. Confirm before building.
4. **WHO growth data size** — full 5-curve tables bundle ~40–60 KB static JSON; acceptable? (Alternative: P3/P50/P97 only.)
5. **Bulk reminder composer** (C9) generates `wa.me` links in bulk but still requires manual tapping per patient — confirmed as the v1 behavior?
