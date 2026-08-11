# Phase 08 — Chat, Notifications & Reminders

**Revision 2.0:** guest chat credentials are server-hashed and cookie-scoped,
emails contain no clinical data, and WhatsApp links record generation rather
than pretending that a manual message was sent.

**Goal:** human support chat on the public site (AI-ready schema, **no AI in
v1**), staff in-app notifications with SSE bell, booking-confirmation emails,
and the WhatsApp one-click reminder composer.

**Depends on:** 02 (models), 03 (booking events), 04 (check-in).
**Blocks:** 09 (inbox UI), 11 (chat widget).

---

## 1. Deliverables

- `services/chat.py`: conversations, messages, unread counters, assignment
- Public chat endpoints (polling) + staff inbox endpoints (SSE)
- `services/notify.py`: in-app notification fan-out + SSE stream
- `services/emailer.py`: SMTP send with AR/EN templates, dev console fallback
- `services/reminders.py`: wa.me composer (per-appointment + bulk day list)
- Widget embed contract for the public site

## 2. Chat — rules

**C1 — Conversation identity.** Logged-in patient → `patient_account_id`.
Guest → `guest_name` + `guest_contact` required on first message. One `open`
conversation per account (reopen reuses it); guests create a new one each time.
The returned guest key is random, stored only as a hash in the database, and
sent in a `Secure`, `HttpOnly`, `SameSite` cookie scoped to the public site/API.
It is never stored in localStorage or returned in every message response.

**C2 — Messages.** `sender_type` ∈ patient/secretary/system (`ai` reserved).
Plain text only in v1, max 2000 chars, HTML-escaped on render. First message
sets `subject` = first 60 chars. Message creation requires an idempotency key
so mobile/network retries cannot duplicate a message.

**C3 — Unread & assignment.** Counters on conversation; inbox sorted by
`last_message_at` desc with unread badge. First secretary reply auto-assigns
(`assigned_to`); others see "handled by X". Close/reopen audited.

**C4 — Realtime.** Staff: authenticated fetch-stream SSE `/api/chat/stream`.
Public widget: **polling**
`GET /api/public/chat/messages?since_id=` every 5s while open (proxy-friendly).

**C5 — Rate limits (public):** 20 msg/min/conversation, 5 new conversations/
day/IP (slowapi; full config in 13).

Guest-cookie chat mutations require the same CSRF token flow as patient account
mutations; the opaque guest cookie is not treated as a CSRF proof.

## 3. Notifications — rules

**N1 — Types:** `chat_new`, `chat_message`, `booking_new`, `booking_cancelled`,
`booking_moved`, `payment_recorded`. Fan-out: secretaries ← booking/chat;
doctor ← own appointment moves/cancels; admin ← all.

**N2 — Delivery:** `notification` rows + authenticated fetch-stream SSE `/api/notifications/stream` (bell
badge + toast). Click → `read_at`. List endpoint with `?unread=` filter.

**N3 — Email (booking confirmation):** on public booking success → write a
deduplicated `outbox_event(kind=email_booking_confirmation)` in the same main
transaction. A restart-safe in-process worker drains it with exponential retry
and marks permanent failures for admin review. The email (if an address exists)
contains clinic name, doctor, date/time, booking_ref, and how to
cancel/reschedule. AR/EN per account locale. It contains no diagnosis,
prescription, lab, imaging, or invoice content. SMTP unset → development log;
email failure never blocks booking.

## 4. WhatsApp reminders — rules

**W1 — One-click (v1), no API integration.** `GET /api/appointments/{id}/reminder-link`
returns `https://wa.me/<phone>?text=…` built from setting
`reminder.whatsapp_template_ar|en` with placeholders `{patient_name}`,
`{doctor_name}`, `{date}`, `{time_or_day}`, `{clinic_name}`, `{clinic_phone}`.
Secretary clicks → WhatsApp opens prefilled → manual send. Server stamps
`reminder_link_generated_at` on link generation and audits
`reminder.link_generated`; it must not claim WhatsApp delivered or that the
patient clicked Send.

**W2 — Bulk:** `GET /api/appointments/reminders/today?doctor_id=` → list of
upcoming bookings with their links; UI shows a checklist (click each → wa.me
opens → tick). True automated bulk is post-v1.

**W3 — Phone normalization:** strip non-digits; leading `0` → replace with
`clinic.country_code` (default `20`). Un-normalizable numbers flagged, no link.

**W4 — Default AR template (seed):**
"أهلاً {patient_name}، معاك عيادة {clinic_name}. بنفتكرك بموعدك مع د. {doctor_name} يوم {date} {time_or_day}. لو محتاج تلغي أو تغيّر الموعد كلمنا على {clinic_phone}."

## 5. API endpoints

**Staff:** `GET /api/chat/conversations?status=` · `GET/POST /api/chat/conversations/{id}/messages` · `POST /api/chat/conversations/{id}/close|reopen` · `GET /api/chat/stream` (SSE).
**Notifications:** `GET /api/notifications?unread=` · `POST /api/notifications/{id}/read` · `POST /api/notifications/read-all` · `GET /api/notifications/stream` (SSE).
**Reminders:** the two endpoints in §4.

**Public:** `POST /api/public/chat/start` `{message, guest_name?, guest_contact?}` + `Idempotency-Key` → sets guest cookie · `GET /api/public/chat/messages?since_id=` · `POST /api/public/chat/messages` `{body}` + `Idempotency-Key`.
Auth: logged-in patient via access token; guest via the HttpOnly cookie described
in C1.

## 6. Widget embed contract (public site, phase 11)

- Floating button: bottom-left in RTL, bottom-right in LTR (away from scrollbar).
- Panel ≤ 360×520: guest name+contact form first time, message list, input.
- Polls per C4; header shows "We reply during working hours" (`clinic.hours_text`).
- Plan/00 colors; z-index below print overlays; fully bilingual.

## 7. Step-by-step tasks

1. `services/chat.py` + staff/public routes + SSE + counters.
2. `services/notify.py` + fan-out wiring into appointment/queue/payment services (replace phase-03 no-op stubs).
3. `services/emailer.py` + AR/EN email templates + outbox worker/retry + booking hook.
4. `services/reminders.py` + both endpoints + normalization tests.
5. Seed: WhatsApp templates (AR per W4 + EN equivalent), hours text.
6. Tests (§8).

## 8. Tests

- Guest start → conversation with guest fields; account start reuses open conversation.
- Counters: patient sends 2 → `unread_staff=2`; secretary list read → resets; SSE event received by staff client.
- C5 limits → 429.
- Fan-out: public booking → every secretary gets `booking_new`; doctor gets `booking_cancelled` on own cancel.
- Email: SMTP unset → rendered email logged; booking still 201.
- Reminder link: Egyptian mobile `010xxxxxxxx` → `wa.me/2010xxxxxxxx`; template placeholders all substituted; `reminder_link_generated_at` stamped; bad number → no link + flag.
- Bulk endpoint returns only future/unchecked bookings.

## 9. Done-when checklist

- [ ] Full loop: guest widget message → secretary SSE ping → reply → widget polls it in ≤5s
- [ ] Bell badge updates live on booking/cancel/payment events
- [ ] Confirmation email renders AR + EN correctly
- [ ] Reminder link opens wa.me with correct Arabic text on desktop + phone
- [ ] C1–C5, N1–N3, W1–W4 test-covered

## 10. Gotchas

- SSE behind nginx: `proxy_buffering off` + heartbeat comments (phase 13 config).
- Guest key must be unguessable (32B urlsafe), hashed at rest, cookie-only, and
  revocable by closing the conversation.
- wa.me text must be URL-encoded UTF-8; test Arabic + emoji survive.
- Don't auto-mark patient messages read when staff merely has the tab open — require the thread to be opened.
