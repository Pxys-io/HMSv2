# Phase 11 — Public Website (`web-public`)

**Revision 2.0:** the public app uses cookie-based refresh safely, submits
idempotency keys for bookings, and treats family profiles as non-deletable
medical identities once history exists.

**Goal:** the patient-facing site: landing page, 3-step booking, patient
account with family profiles, and the support-chat widget. **Separately
deployable** — it talks only to `/api/public/*` and can be rebuilt/redeployed
without touching anything else.

**Depends on:** 03 (public booking API), 08 (chat), 00 (design).
**Blocks:** 13 (deploy config covers both sites).

---

## 1. Deliverables

- Landing page (sections §4.1)
- Auth: register/login (email or phone), token handling
- Booking flow `/book/*` (3 steps + confirmation)
- Account area `/account/*`: upcoming/past appointments, cancel/reschedule, family profiles CRUD
- Chat widget (per Plan/08 §6)
- SEO basics + bilingual from day one (strings structured; AR filled in 12)

## 2. Architecture notes

- Own Vite app, own build, own nginx server block. **No code imports from
  `web-staff`** — duplication of small UI bits is accepted (independence > DRY here).
- API client reads base URL from `VITE_PUBLIC_API_URL` (dev: proxied `/api`).
- Access tokens in memory only; rotating refresh cookies are `HttpOnly`,
  `Secure`, `SameSite`, and paired with a CSRF token for mutations. No auth,
  patient, appointment, or chat credential is stored in localStorage. Non-
  sensitive UI preferences may use localStorage.
- All API requests that use the refresh cookie set `credentials: "include"`;
  the API client obtains a CSRF token before the first mutation and sends it in
  `X-CSRF-Token`.
- Routes: `/` landing, `/book/*`, `/login`, `/register`, `/account/*`, `/chat` handled by widget.

## 3. Public API surface consumed (already built in 03/08)

`GET /api/public/branding` (name, public logo asset, hours, address, phones, about, services) · `GET /api/public/assets/{id}` (public-safe image only) —
add this tiny endpoint in this phase if not present · `GET /api/public/doctors` ·
`GET /api/public/doctors/{id}/availability` · `GET /api/public/visit-types` ·
auth register/login/me · `GET/POST /api/public/profiles` (resource writes require `Idempotency-Key`; +PATCH/POST archive; no hard DELETE after clinical history) ·
appointments book/list/cancel/move · chat start/messages.

## 4. Pages

### 4.1 Landing `/`

Marketing personality per Plan/00 (spacious, warm). Sections in order:

1. **Hero** — clinic name, one-line promise, "احجز الآن / Book now" CTA → `/book`, phone number with `tel:`, subtle gradient (brand-50 → white), real photo placeholder slot.
2. **Trust strip** — hours today (from settings, computed open/closed now), address + map link, WhatsApp icon link.
3. **Services** — cards from `public.services(_ar)` settings.
4. **Doctors** — cards (photo, name, title, specialty, bio excerpt) → per-doctor "Book with Dr. X" (prefills `/book?doctor=`).
5. **How booking works** — 3 numbered steps with icons.
6. **Location** — embedded map iframe (`clinic.location_url`) + address + parking note.
7. **Footer** — hours table, contacts, quick links, language switch, "Powered by HMSv2" (small, removable via setting).

### 4.2 Booking `/book/*` — 3 steps + done

Slim header: logo + step indicator (1 Doctor · 2 Time · 3 Details). Progress
preserved in URL params (refresh-safe).

- **Step 1 — Doctor:** doctor cards (same data as landing). If `?doctor=` prefilled, skip.
- **Step 2 — Time:** mode-aware:
  - slots mode → date strip (next 14 days, unavailable days disabled) + slot grid (chips, taken slots hidden — only available returned by API).
  - day_queue mode → date strip only + explainer: "الحجز باليوم، والدور بأولوية الوصول / Booking is per day; order is by arrival".
- **Step 3 — Details:** if logged in → pick family profile (radio cards + "add member"); else → login/register inline (name + phone-or-email + password). Confirm summary card (doctor, date/time, visit type, price hint if public). Submit with a new `Idempotency-Key`; retries must reuse the same key.
- **Done:** big booking_ref (`BK-XXXXXXXX`), "add to calendar" (generate `.ics` client-side), what-to-expect text, account link. Email fires server-side (08).

### 4.3 Account `/account/*`

- **Upcoming** — cards: doctor, date/time, ref; actions: reschedule (same flow as book, prefilled) and cancel (confirm + optional reason). Both actions generate and retain an `Idempotency-Key` through retries.
- **Past** — status badges incl. no-show (friendly copy).
- **Family** — profile cards (name, age, gender, phone), add/edit member (name, gender, birth date, phone; optional allergies — framed as "helps your doctor"). Profiles with clinical history are archived/deactivated, never hard-deleted; profiles with future appointments cannot be archived until the appointments are resolved. The public account never sees allergies, diagnoses, visits, attachments, or invoices.

### 4.4 Chat widget

Per Plan/08 §6. Guest flow: name + phone collected in-widget; guest credential
is an HttpOnly cookie managed by the API. Logged-in skips straight to
messaging. Unread dot on the bubble via polling.

## 5. UX/SEO requirements

- Bilingual toggle in header (persists cookie/localStorage); `dir` flips; hreflang `ar`/`en` link tags; Arabic-first default (D7).
- Meta: title/description per page both locales, OpenGraph (clinic name, hero image), `application/ld+json` `MedicalClinic` schema (name, address, phone, hours).
- Mobile-first (most patients book from phones); 44px targets; sticky bottom "Book" bar on landing mobile.
- Performance: LCP < 2.5s on 4G; images lazy; fonts display=swap; total JS ≤ 250KB gzip.
- Accessibility: AA contrast, labeled inputs, focus visible, error summaries on forms.

## 6. Step-by-step tasks

1. Shell + tokens + header/footer + locale switch + routing.
2. Branding endpoint (if missing) + landing sections (static → settings-driven).
3. Auth pages + account layout + guards.
4. Profiles CRUD UI.
5. Booking flow (mode-aware) + confirmation + .ics.
6. Chat widget per contract.
7. SEO/meta/ld+json + performance pass.
8. Tests (§7).

## 7. Tests

- Booking happy path both modes (msw-mocked API): slots shows grid, day_queue shows explainer; confirmation shows ref.
- Auth guard: /account redirects; booking step 3 inline register works.
- Family: add member → appears in booking step 3 radio list.
- Cancel: calls API, list refreshes; past no-show renders badge.
- Widget: guest start receives a cookie; poll appends staff reply (mock fetch).
- RTL snapshot: `dir=rtl` renders mirrored layout (visual check via storybook-less fixture page).

## 8. Done-when checklist

- [ ] Full patient journey works end-to-end against the real backend: land → book → email → account → reschedule → cancel → chat
- [ ] Site builds and runs standalone (backend + nginx static only)
- [ ] Both locales render correctly with mirrored layout
- [ ] Budgets in §5 met
- [ ] No call outside `/api/public/*` anywhere in the bundle (grep the build)
- [ ] No patient/appointment/refresh/chat credential is stored in localStorage

## 9. Gotchas

- Day-strip dates must be clinic-local (fetch server "today" from availability response header/field, don't trust device clock).
- The .ics generator needs correct TZID (`Africa/Cairo`) floating-time pitfalls.
- Guest chat cookie loss = new conversation (by design, C1) — widget copy should nudge guests to leave their number.
- Keep this app deployable from its own folder: CI builds `web-public/dist` independently; never import backend-only env names.
