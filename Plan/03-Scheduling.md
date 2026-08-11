# Phase 03 — Scheduling

**Revision 2.0:** booking now has explicit idempotency, concurrency, ownership,
and public-data rules. The availability calculation is the only authority for
both preview and commit.

**Goal:** the booking brain: doctor shifts, blocked days, visit types, the
hybrid availability engine (exact slots **or** day+queue per doctor), and the
appointment lifecycle (book / move / cancel / no-show / follow-up link) for
both staff and public APIs.

**Depends on:** 02. **Blocks:** 04 (queue), 06 (billing uses visit_type pricing).

---

## 1. Deliverables

- CRUD: visit types, doctor schedules, schedule blocks (admin/doctor-self)
- Availability service: `slots` mode and `day_queue` mode, capacity-aware
- Appointment service + routes (staff + public), follow-up linking
- Public availability + booking endpoints (unauthenticated availability read; authenticated booking)
- Email-confirmation hook (fires event; actual email in phase 08)

## 2. Rules (business logic, binding)

**R1 — Shifts.** A doctor is bookable only inside `doctor_schedule` intervals
for that weekday (respecting `effective_from/to`, `is_active`).

**R2 — Blocks.** Any `schedule_block` overlapping a date removes the whole
date (v1: blocks are date-granular, not time-granular).

**R3 — Slots mode.** Slot length = `visit_type.duration_minutes` if set else
`doctor.default_slot_minutes`. Candidate starts step by (slot length +
`buffer_minutes`) within each shift interval. A start is offered only if the
whole [start, start+len) fits inside one shift interval.

**R4 — Capacity.**
- Slots mode: active appointments at a given start < `slot_capacity` (default 1).
- Both modes: active appointments on that date < `day_capacity` (if set).
- Public API never exceeds capacity. Staff may exceed with `force=true` (audited, UI shows warning).

**R5 — day_queue mode.** Booking stores `date` only (`start_time = null`).
Availability = date bookable + under day capacity. Arrival order is decided at
check-in (phase 04), never at booking time.

**R6 — Horizon.** Public booking allowed from "today" up to `booking_horizon_days`
(setting, default 30). Staff unrestricted.

**R7 — Status machine.**
```
booked → checked_in → in_progress → completed
booked → cancelled            (patient or staff, before check-in)
booked → no_show              (staff, end of day)
checked_in → cancelled        (staff only, with reason; queue entry → left)
```
`completed` is set by the visit workflow (phase 05), not manually.

**R8 — Follow-up.** `appointment.follow_up_of_id` links a new booking to a past
appointment. When created from a visit's `follow_up_due` (phase 05/07), the link
is required; staff may also link manually.

**R9 — Reschedule = move.** Changing date/time keeps the same `booking_ref`
(history preserved in audit). Cancel creates a terminal state; patient rebooks
to get a new ref.

**R10 — No-show.** Marking `no_show` increments `patient_profile.no_show_count`
(service-level, audited). Cancelling a no-show is not allowed; create a new
appointment instead. A transition can execute only once.

**R11 — Idempotency.** Every create/move/cancel/no-show request requires an
`Idempotency-Key`. A network retry with the same key and identical request body
returns the original response; reuse with a different body is `409`. Public
booking keys are scoped to the patient account (or a short-lived anonymous
booking session).

**R12 — Ownership.** Patient endpoints may only see or mutate appointments for
profiles linked to their account. Staff routes return only the fields needed by
the role; public doctor data excludes phone, internal rates, schedule notes, and
patient counts.

## 3. API endpoints

### 3.1 Staff (`/api/*`)

| Method & path | Role | Purpose |
|---|---|---|
| `GET/POST /api/visit-types` · `PATCH /api/visit-types/{id}` | admin | visit type CRUD |
| `GET/POST /api/doctors/{id}/schedules` · `PATCH/DELETE /api/schedules/{id}` | admin, doctor(self) | shifts |
| `GET/POST /api/doctors/{id}/blocks` · `DELETE /api/blocks/{id}` | admin, doctor(self) | blocked days |
| `GET /api/availability/{doctor_id}?date=&visit_type_id=` | any staff | availability for picker |
| `GET /api/appointments?doctor_id&date&status&page` | any staff | day lists / calendar feed |
| `POST /api/appointments` | secretary, admin | staff booking (any profile; `force` allowed, audited) |
| `GET /api/appointments/{id}` | any staff | detail incl. patient chip |
| `POST /api/appointments/{id}/move` | secretary, admin | `{date, start_time?}` — validates per §2 |
| `POST /api/appointments/{id}/cancel` | secretary, admin | `{reason}` |
| `POST /api/appointments/{id}/no-show` | secretary, admin | increments profile counter |
| `GET /api/patients/{id}/appointments` | any staff | per-patient history |

### 3.2 Public (`/api/public/*`)

| Method & path | Auth | Purpose |
|---|---|---|
| `GET /api/public/doctors` | none | bookable doctors (name, specialty, title, photo, bio, mode) |
| `GET /api/public/doctors/{id}/availability?from=&to=&visit_type_id=` | none | per-day availability (slots list or day flags) |
| `GET /api/public/visit-types?doctor_id=` | none | types + public prices for that doctor |
| `POST /api/public/appointments` | patient | book for one of own profiles `{profile_id, doctor_id, visit_type_id, date, start_time?}` + required idempotency key |
| `GET /api/public/appointments` | patient | own upcoming + past |
| `POST /api/public/appointments/{id}/cancel` | patient | own only, before check-in |
| `POST /api/public/appointments/{id}/move` | patient | own only; validates like booking |

Public availability responses are cached 30s in-process (simple dict cache) to
survive landing-page traffic spikes.

## 4. Availability engine (`services/availability.py`)

```
def day_availability(doctor, date, visit_type) -> DayAvailability:
    if blocked(doctor, date): return UNAVAILABLE(reason="block")
    shifts = active_shifts(doctor, weekday(date))
    if not shifts: return UNAVAILABLE(reason="no_shift")
    if doctor.day_capacity and active_count(doctor, date) >= doctor.day_capacity:
        return UNAVAILABLE(reason="capacity")
    if doctor.booking_mode == "day_queue":
        return DayAvailability(mode="day_queue", date=date, remaining=capacity_left)
    # slots mode
    length = visit_type.duration_minutes or doctor.default_slot_minutes
    step = length + doctor.buffer_minutes
    slots = []
    for (s, e) in merge(shifts):
        t = s
        while t + length <= e:
            taken = active_count_at(doctor, date, t)
            if taken < doctor.slot_capacity and not in_past(date, t):
                slots.append(Slot(start=t, end=t+length, remaining=slot_capacity-taken))
            t += step
    return DayAvailability(mode="slots", date=date, slots=slots)
```

- "in_past" compares clinic-local now + 10 min grace.
- Bookings validate by re-running the same function inside the transaction
  (single source of truth — no separate "check" logic to drift).
- Concurrency: `SELECT … FOR UPDATE` on the doctor+date capacity path; on SQLite
  this degrades to a short write transaction with one retry. The public endpoint
  never returns success until the appointment row is committed.

## 5. Step-by-step tasks

1. Schemas for visit types, schedules, blocks, appointments (request/response),
   including an idempotency key and public/staff response projections.
2. `services/availability.py` + unit tests with a fake clock (freeze clinic "now").
3. `services/appointments.py`: book/move/cancel/no-show with audit events
   (`appointment.create|move|cancel|no_show`), capacity checks, ref generation
   (`BK-` + 8 random alnum, collision-retried).
4. Staff routes (§3.1) incl. per-day calendar feed query (join profile name/phone).
5. Public routes (§3.2) + 30s availability cache + rate-limit hooks (full limiter in 13).
6. Notification hooks: `booking_new` → notify all secretaries (in-app; implemented phase 08 — here just call a no-op service stub), email-confirmation event stub.
7. Seed: demo doctor gets Mon/Wed 17:00–21:00 shifts, one block next week, 3 visit types (Consultation 20m/300, Follow-up 10m/150, Procedure 60m/800), one day_queue-mode second doctor.

## 6. UI/UX notes (implemented in phases 09/11; API must support them)

- Secretary calendar: week view per doctor, chips colored by `visit_type.color`, status badge per Plan/00 §2.3.
- Staff booking modal: PatientSearchBox → visit type → date → slot grid (slots mode) or day confirm (day_queue) → optional follow-up link → force checkbox only when capacity blocks.
- Public booking: 3 steps (doctor → time → profile) — spec in Plan/11 §5.

## 7. Tests

- Slots generation: shift 17:00–21:00, len 20, buffer 0 → starts 17:00…20:40 (12 slots); buffer 10 → 17:00, 17:30, …
- Block removes date; expired shift (`effective_to` yesterday) ignored.
- Capacity: slot_capacity=1 → second public booking same start → 409 `CONFLICT`; staff `force=true` succeeds + audit flag.
- day_capacity: reached → public 409; day_queue booking has `start_time is None`.
- Move to blocked day → 409; move keeps `booking_ref`.
- Cancel after check-in by patient → 403; by staff → ok with reason; audit rows exist for every transition.
- No-show increments profile counter exactly once (repeat call → 409).
- Follow-up: creating appointment with `follow_up_of_id` persists link; recall query (phase 07) will rely on it.
- Public endpoints: unauthenticated availability OK; booking without token → 401; booking someone else's profile → 403.
- Idempotency: retry returns the original booking without a duplicate; changed payload with the same key → 409.
- Concurrent two-client booking for the last slot → exactly one 201 and one 409.

## 8. Done-when checklist

- [ ] Both booking modes work end-to-end via API (staff + public)
- [ ] R1–R12 each covered by at least one test
- [ ] Calendar feed returns a day with mixed statuses correctly
- [ ] All transitions audited (chain verify green)
- [ ] Duplicate network submissions cannot create duplicate appointments
- [ ] Seed data produces a bookable demo doctor on next Monday

## 9. Gotchas

- All "today/tomorrow" logic uses `CLINIC_TZ`, never server-local time.
- `end_time` always derived & stored (reporting needs it); recompute on move.
- Deleting a visit type used by appointments → forbid (409); deactivate instead.
- A doctor changing `booking_mode` with future bookings: allow, but existing bookings keep their times (slots become informational); warn in UI (phase 09).
- A walk-in in slots mode counts against the doctor's day capacity, but not a particular slot; this is explicit in the response so reception understands why later capacity can close.
