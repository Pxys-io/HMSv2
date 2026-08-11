# Phase 04 — Queue & Waiting Room

**Revision 2.0:** queue completion is now owned by the visit workflow; queue
state cannot mark a medical visit complete without a completed visit record.
TV output is operational and privacy-minimized.

**Goal:** same-day reality: check-in, arrival-ordered queue per doctor,
walk-ins, the realtime waiting-room board (SSE) for reception, doctor "call
next", and a public-facing TV display mode.

**Depends on:** 03. **Blocks:** 05 (visit starts from queue), 06 (hourly billing
uses visit timings copied from the queue).

---

## 1. Deliverables

- `services/queue.py`: check-in, walk-in insert, call/start/finish/leave, reorder
- SSE stream endpoint for the board + TV
- Board API snapshot endpoint (initial load; SSE for deltas)
- End-of-day sweep: remaining `booked` → mark `no_show` (bulk action)
- UI spec for the reception board & TV mode (built in 09; contracts defined here)

## 2. Rules (binding)

**Q1 — One queue per (doctor, date).** `seq` = monotonically increasing arrival
order, assigned at check-in (`max(seq)+1` inside transaction).

**Q2 — Check-in sources:**
- Reserved patient: secretary clicks check-in on the appointment → appointment
  `booked → checked_in`, queue entry created (`status=waiting`).
- Walk-in: secretary picks/creates patient profile + visit type → appointment
  row created with `source=walk_in` (slots mode doctors: `start_time=null`,
  flagged `walk_in`) → immediately checked in + queued.
- Patient self check-in (public site): **not in v1**.

**Q3 — Hybrid doctors.** Both modes share the same queue mechanics. For
slots-mode doctors the board also shows the booked time; secretary may check in
early/late — arrival order still rules (that's the clinic's chosen model), but
the board flags late arrivals (booked 10:00, arrived 10:25 → late badge).

**Q4 — Status flow:**
`waiting → called → in_room → completed`. `left` = patient left without being
seen (secretary action; a checked-in appointment becomes `cancelled` with
reason `left_after_check_in`; an untouched booked appointment becomes
`no_show`).

**Q5 — Call next:** doctor (or secretary on their behalf) → oldest `waiting`
becomes `called` (+`called_at`); "start visit" flips to `in_room` and creates
the `visit` row (phase 05). Only one `in_room` per doctor (service-enforced).
The queue remains `in_room` until the doctor completes the visit; only then do
the visit, queue entry, and appointment transition to `completed`.

**Q6 — Reorder:** secretary may move a waiting entry up/down (manual seq swap,
audited) — e.g. emergency first. Doctor's "call specific patient" allowed too.

**Q7 — Timings:** `started_at`/`ended_at` on the queue entry feed wait-time
stats. The visit's `started_at`/`ended_at` is the billing source of truth; the
service copies the same timestamps when the visit starts/completes.

**Q8 — End of day:** secretary clicks "Close day" (or admin): all `waiting`
entries → `left` and their linked appointments → `cancelled` with reason
`left_after_check_in`; all untouched `booked` appointments → `no_show`
(counter increments once each; audited). In-room entries are exceptions and
must be resolved by the doctor/admin. Nothing auto-runs without a click in v1.

**Q9 — Idempotency.** Check-in, walk-in, call, start, leave, reorder, and
close-day requests require an `Idempotency-Key`; a retry returns the original
state transition. A stale queue snapshot cannot move a patient twice.

## 3. API endpoints (`/api/queue/*`)

| Method & path | Role | Purpose |
|---|---|---|
| `GET /api/queue?doctor_id&date` | staff | board snapshot (entries + patient chips + booked-not-arrived list) |
| `POST /api/queue/check-in` | secretary, admin | `{appointment_id}` |
| `POST /api/queue/walk-in` | secretary, admin | `{profile_id or new_profile{...}, doctor_id, visit_type_id}` |
| `POST /api/queue/{id}/call` | doctor(self), secretary | entry → called |
| `POST /api/queue/call-next` | doctor(self), secretary | oldest waiting → called |
| `POST /api/queue/{id}/start` | doctor(self) | → in_room; creates `visit` (phase 05 hook) |
| `POST /api/queue/{id}/complete` | doctor(self) | compatibility action only when the linked visit is completed; normally called by `POST /api/visits/{id}/complete` |
| `POST /api/queue/{id}/leave` | secretary, admin | `{outcome: "cancelled"|"no_show", reason?}` |
| `POST /api/queue/{id}/move` | secretary, admin | `{direction: up|down}` waiting-only reorder |
| `POST /api/queue/close-day` | secretary, admin | `{doctor_id, date}` sweep per Q8 |
| `GET /api/queue/stream?doctor_id&date` | staff SSE | deltas: `entry_added|updated|removed|snapshot` |

**TV display:** `GET /api/queue/display/{doctor_id}` — **tokenized, no login**:
admin generates a per-doctor display token (stored only as a hash, returned once
to the admin; random 32 bytes). Returns `{now_calling: seq+name-first-only,
waiting_count}`.
Plus SSE variant `/api/queue/display/{doctor_id}/stream`. Shows **first name +
seq only** (privacy). Rate-limited leniently (it's one TV).

## 4. SSE design

- `sse-starlette`. Staff clients connect through an authenticated `fetch()`
  streaming reader (not native `EventSource` with a token in the URL). Event
  payload contains operational fields only (queue number,
  first name, visit type, status, timestamps); never phone, clinical text,
  diagnoses, attachments, or invoice amounts. Client applies
  to local state; on reconnect client refetches snapshot (Last-Event-ID not
  required v1 — snapshot-on-connect is sent first).
- Heartbeat comment every 15s (`: ping`) so nginx doesn't buffer-close.
- One in-process broadcaster (dict of doctor+date → set of queues). Single
  process = fine for v1; documented as such.

## 5. UI spec (build in 09; contracts here)

**Reception board (`/reception/board`):**
- Doctor tabs across top; per doctor: three columns **Waiting** (seq, first
  name, WaitTimer, late badge if applicable, visit-type chip) · **In room**
  (current + elapsed) · **Completed** (last 5, collapsed).
- Below: **Booked, not arrived** strip (today's remaining bookings with one-click
  check-in + WhatsApp reminder icon).
- Primary actions per row: check-in → waiting → call → start (doctor) → complete
  from the exam screen.
  Secondary: move up/down, leave, open profile.
- New walk-in button opens modal: PatientSearchBox or "new profile" mini-form
  (name, gender, phone required only) + visit type → confirm.
- Queue position/status actions may be optimistic; check-in/start/leave/complete
  wait for server acknowledgement and SSE reconciles. Sounds: soft chime on `called`
  (toggleable, off by default).

**TV mode (`/display/{doctor_id}?token=…`):** fullscreen, huge mono seq number
(`Now calling: 7`), optional first name only if the clinic setting explicitly
allows it, waiting count, clinic name, auto-RTL, dark background `#0F172A` with
brand accents, no controls. Never show a full name, phone, diagnosis, or
financial data. 200ms transitions per Plan/00 §8.
The display route sends `Referrer-Policy: no-referrer`, never logs the token in
the page, and rotation invalidates the previous token immediately.

## 6. Step-by-step tasks

1. `services/queue.py` with Q1–Q9 + audit events (`queue.check_in`, `queue.walk_in`, `queue.call`, `queue.start`, `queue.complete`, `queue.leave`, `queue.reorder`, `queue.close_day`).
2. Snapshot + mutation routes; SSE broadcaster + stream routes (staff + display).
3. Display token generation in settings service (admin endpoint `POST /api/doctors/{id}/display-token` → returns/rotates).
4. Seed helper: script to fake a clinic day (book 6, check in 4, walk-in 2) for board testing.
5. Tests (§7).

## 7. Tests

- Check-in twice → 409; walk-in creates profile (when new) + appointment + queue entry atomically.
- seq monotonic per (doctor,date); two doctors same day independent.
- call-next picks oldest waiting; second `in_room` attempt → 409.
- leave → appointment terminal state per outcome; no_show increments counter once.
- visit completion → queue `completed` + appointment `completed`; attempting queue completion before visit completion → 409.
- close-day: waiting → left; untouched booked → no_show; in-room entries are surfaced as an exception and never silently closed; completed untouched; idempotent (second call no-op).
- SSE: connect → receives snapshot; mutation → delta received by second client.
- Display endpoint: wrong token 403; payload contains no phone/full name.
- Display endpoint: token is hashed at rest, rotatable, and revocation takes effect immediately.
- Reorder swaps seq and emits audit row with before/after seqs.
- Retrying check-in/start/complete with the same key does not create a second queue entry or visit.

## 8. Done-when checklist

- [ ] Full day simulated via API: book → check-in → call → start → complete visit → close-day
- [ ] SSE deltas reach 2 concurrent clients; snapshot-on-connect works
- [ ] TV display renders privacy-safe payload with token
- [ ] Q1–Q9 each test-covered
- [ ] Audit chain green after a simulated day

## 9. Gotchas

- SQLite write lock under concurrent check-ins: keep transactions short; retry once on `OperationalError: database is locked`.
- `called` without `start` is a real state (doctor called, patient late to door) — don't auto-timeout it in v1.
- Walk-ins on slots-mode doctors get `start_time=null` — availability engine must not count them against slot capacity (they're already inside the clinic).
- Board date defaults to clinic "today" — after midnight the board flips; warn at 23:55 is overkill, skip.
- Never let a secretary mark an in-room queue entry completed without a doctor-completed visit; use `left` or an explicitly audited administrative exception instead.
