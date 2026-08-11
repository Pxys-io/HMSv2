# Phase 07 — Printables, Recall & Global Search

**Revision 2.0:** printable clinical documents are permissioned and sanitized,
recall actions are idempotent, and quick search returns only the minimum
operational data needed to identify a patient.

**Goal:** three speed/trust features: printable documents on clinic letterhead
(روشتة, report, sick-leave, referral, invoice), the follow-up **recall list**
with no-show stats, and the **⌘K global patient search**.

**Depends on:** 05 (Rx, follow_up_due), 06 (invoice print). **Blocks:** 09
(staff frontend consumes all three).

---

## 1. Deliverables

- `services/printing.py`: render context builders + HTML rendering for 5 doc types × 2 locales
- Print template admin API (edit letterhead templates)
- Printable routes consumed by the staff app's `/print/*` pages
- `services/recalls.py`: recall list query + no-show surfacing
- `services/search.py`: patient quick search
- Print CSS implementing Plan/00 §10

## 2. Printables — rules

**P1 — Doc types & content:**

| key | Size | Content |
|---|---|---|
| `rx` | A5 | letterhead, patient (name/age/code), date, diagnoses (final only, optional toggle), Rx items table (drug, dose, freq, duration, instructions), doctor name/specialty, signature line |
| `report` | A4 | letterhead, "To whom it may concern" body: complaint/findings/diagnosis/plan snapshot (doctor picks fields via checkboxes before print), signature |
| `sick_leave` | A4 | patient, date range, rest-days count, diagnosis optional (privacy toggle), doctor signature |
| `referral` | A4 | patient, referred-to (specialty/doctor free text), reason, summary, signature |
| `invoice` | A5 | invoice number/date, items, totals, discount, payments, remaining, syndicate split, cashier name |

**P2 — Templates.** `print_template(key, locale)` holds `body_html` with
allowlisted `string.Template` placeholders only: `${clinic.name}`,
`${patient.name}`, `${rx.items_table}`… Letterhead is global (logo + names +
address + phones from settings), not per template. Admin edits templates in
settings UI with live preview (dummy data); the server sanitizes the result and
rejects scripts, event handlers, external URLs, arbitrary CSS, and unknown
placeholders.

**P3 — Rendering.** Server route `GET /api/print/{key}/{entity_id}?locale=ar`
returns a **complete standalone HTML page** (inline CSS, system+embedded fonts,
`dir` per locale, auto `window.print()` on load, white bg). Staff frontend opens
it in a new tab. No PDF generation in v1 (browser "Save as PDF" covers it).

**P4 — Authorization.** Print routes require staff auth. Doctor/admin may
compose clinical reports, sick-leave, and referrals. Secretary may print an
already-completed prescription or invoice, but cannot compose clinical text or
download raw clinical attachments. Every print access is audit-logged.

**P5 — Locale.** `locale` param selects template + direction + labels; default
from patient account locale, fallback `ar`.

## 3. Recall & no-show — rules

**R1 — Recall list:** profiles where latest visit with `follow_up_due <=
today + lookahead_days` (setting, default 7) AND no active future appointment
for that profile. Columns: profile chip, phone, doctor, due date, days overdue
(red) / due-in (amber), last visit summary line, actions: WhatsApp remind
(wa.me composer, phase 08), book appointment (modal), dismiss (snooze N days —
`recall_dismissed_until` on visit; add column Date nullable). Dismiss requires
an idempotency key and is recorded in the audit protocol.

**R2 — No-show stats:** `patient_profile.no_show_count` already maintained
(phase 03). Surface: booking modals show "no-shows: N" warning chip when N≥2;
patient page shows no-show rate = no_show / (completed + no_show).

## 4. Search — rules

**S1 — Endpoint:** `GET /api/search/patients?q=&limit=8` (staff only; clinical
fields are never returned and the lookup is access-audited).
Matches: `code` exact-prefix, `full_name`/`full_name_ar` substring
(case-insensitive), `phone` substring (digits-only normalized). Ranking: code
exact > phone exact > name starts-with > name contains. Response: code, names,
phone, age, gender, no_show_count, syndicate name.

**S2 — ⌘K palette (frontend contract):** opens anywhere (`⌘K`/`Ctrl+K`),
debounced 150ms, min 2 chars, arrows+enter, recent selections held in memory
for the current tab only (never localStorage), "new patient" action at bottom.
Also searches **appointments today**
by patient name (secondary group). Implementation lives in 09; this endpoint
is its only data dependency.

## 5. Step-by-step tasks

1. `services/printing.py` context builders per doc type + HTML shell (inline CSS from a `print.css` template implementing Plan/00 §10).
2. Seed default templates AR+EN for all 5 keys (clean medical look; AR templates RTL).
3. Print routes + template admin CRUD (`GET/PUT /api/print-templates`) with server-side sanitization and an allowlisted placeholder registry.
4. `services/recalls.py` + `GET /api/recalls?lookahead=` + `POST /api/recalls/{visit_id}/dismiss`.
5. `services/search.py` + endpoint; DB index on `lower(full_name)` not needed at this scale — substring scan over a few thousand profiles is fine; note index for prod Postgres (`pg_trgm`) in 13.
6. Tests (§6).

## 6. Tests

- Each doc type renders 200 HTML containing patient name, clinic name, `dir="rtl"` for `ar`; unauthorized roles cannot compose/download clinical content.
- Placeholder escaping: patient named `<b>` renders escaped.
- Template edit persists and changes output; invalid key → 404.
- Template containing `<script>`, an event handler, external URL, or unknown placeholder → 422 and is not saved.
- Recall: due+no-future-appointment appears; booked tomorrow → disappears; dismiss snoozes.
- No-show rate math on fixture.
- Search: by code prefix, by phone substring, Arabic name substring; limit 8; ranking order fixture.
- Print auth: patient token → 403.

## 7. Done-when checklist

- [ ] All 5 doc types print correctly in AR + EN from browser print dialog
- [ ] Recall list matches SQL fixture; dismiss works
- [ ] ⌘K endpoint < 50ms on 5k profiles (SQLite)
- [ ] Templates editable without server restart
- [ ] Audit rows: template edits, recall dismissals
- [ ] Print access and recall actions are present in the audit chain

## 8. Gotchas

- Arabic shaping in print = browser's job (we output HTML, not PDF) — always test Chrome print preview.
- `window.print()` auto-call must be behind a `<script>` that waits for fonts (`document.fonts.ready`).
- Keep print HTML self-contained (no external requests) — clinic PCs may be offline.
- Invoice print must show `remaining = patient_due − (paid_total − refunded_total)`, never just total.
