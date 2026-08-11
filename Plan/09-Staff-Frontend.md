# Phase 09 — Staff Frontend (`web-staff`)

**Revision 2.0:** the staff client follows the safer auth/storage contract,
never treats clinical autosave as last-write-wins, and separates attachment
metadata from protected file content.

**Goal:** the complete internal app: secretary workspace, doctor workspace,
admin workspace — built on the design system (Plan/00) and the APIs from
phases 02–08.

**Depends on:** 02–08 (APIs), 00 (design). **Blocks:** 10 (PWA enhances this app).

---

## 1. Deliverables

- App shell (Plan/00 §5.1) with role-based sidebar
- All screens in §4, fully functional against the API
- UI kit per Plan/00 §6.1–6.2 (built first, in Storybook-less catalog page `/ui-catalog` visible in dev only)
- Auth flow: login, token refresh interceptor, route guards per role
- TanStack Query data layer + SSE wiring (queue board, notifications, chat)
- Forms: react-hook-form + zod schemas mirroring API contracts

## 2. Architecture

```
src/
├── api/            # fetch client (auth header, refresh retry, error→AppError)
├── components/ui/  # Plan/00 §6.1 primitives
├── components/     # Plan/00 §6.2 domain components
├── features/
│   ├── auth/  ├── calendar/  ├── board/  ├── patients/
│   ├── exam/  ├── cashier/  ├── recalls/  ├── chat/
│   ├── reports/  ├── admin/  └── settings/
├── routes.tsx      # role-guarded routes
├── stores/         # tiny zustand stores (sidebar, locale) — server state stays in Query
└── styles/         # tokens.css (from 01), print helpers
```

- Data: TanStack Query; authenticated `fetch` streaming hooks update query
  caches (`useQueueStream`, `useNotifyStream`, `useChatStream`). Do not use
  native `EventSource` with a token in the URL.
- Auth: access token remains in memory; refresh is an HttpOnly cookie. The fetch
  client sends the CSRF header for cookie mutations and retries one refresh,
  never writing tokens to localStorage.
- Mutations: optimistic only for queue position/status and chat send;
  appointment, payment, and clinical writes wait for server acknowledgement.
- Errors: API `detail.code` mapped to translated messages; 401 → silent refresh once → else login redirect.

## 3. Global UX requirements

- Every list screen: URL-synced filters (shareable links), pagination, empty state per Plan/00 §6.3.
- Every mutating button: loading state; destructive → confirm dialog (Plan/00 component).
- Keyboard: `⌘K` palette (phase 07 endpoint) globally; `g then b/c/p/x` nav shortcuts (board, calendar, patients, cashier); forms submit `Ctrl+Enter`.
- Sidebar remembers collapse; locale switch instant (i18next, phase 12 strings wired as we go — no hardcoded text anywhere).

## 4. Screens

### 4.1 Auth
`/login` — centered card, email+password, error inline, clinic name/logo from `/api/public/branding` (name/logo/hours only — **this endpoint is added in this phase**, reused by the public site in 11). Redirect to role home: secretary→/board, doctor→/today, admin→/reports/daily.

### 4.2 Secretary workspace

- **`/board` (home)** — waiting-room board per Plan/04 §5. Walk-in modal, check-in, reorder, leave, close-day. Doctor tabs show per-doctor counts.
- **`/calendar`** — week grid per doctor (schedule blocks shaded), day column of appointment chips (color = visit type, badge = status). Click → appointment drawer (details, move = drag or picker, cancel with reason, WhatsApp remind icon, no-show mark). "New booking" modal per Plan/03 §6.
- **`/patients`** — searchable table (code, name, phone, age, syndicate, no-show count, last visit). Row → `/patients/{id}`: profile card (demographics editable by secretary; clinical alerts only by doctor/admin), appointments tab, invoices tab, attachment **metadata** tab (no clinical file download for secretary), clinical tabs hidden (E2).
- **`/cashier`** — per Plan/06 §4 (to-collect list, pay modal, invoice drawer, manual invoice button).
- **`/recalls`** — table per Plan/07 §3 R1 with WhatsApp + book + dismiss actions.
- **`/chat`** — two-pane inbox (conversation list + thread), reply box, close/reopen, guest badge, "handled by" label. SSE live.
- **`/reports/daily`** — secretary-scoped daily revenue view.

### 4.3 Doctor workspace

- **`/today`** — own queue board (simplified: waiting list + call-next + start), own upcoming bookings, quick stats (seen/remaining/earnings today).
- **`/exam/{visitId}`** — the exam screen per Plan/00 §5.2 + Plan/05 §4 (sacred layout, versioned autosave, conflict review, protected file access, print menu, complete→invoice).
- **`/schedule`** — own shifts read view + request block (creates block if admin allowed doctor-self per role guard; else shows "ask admin" hint). v1: doctor can edit own shifts/blocks.
- **`/my/finance`** — own doctor-share report + own invoices list (read-only).

### 4.4 Admin workspace

- **`/admin/users`** — staff table, create/edit modal (role, doctor sub-form when role=doctor: booking mode, slot config, billing), deactivate, reset password.
- **`/admin/pricing`** — visit types CRUD + price matrix grid (rows visit types, columns doctors, cells editable) + per-hour rates.
- **`/admin/syndicates`** — list + detail (syndicate-coverage/patient-share editor same grid pattern, contact info).
- **`/admin/audit`** — filter bar (date range, actor, action prefix, entity), table, row → JSON before/after diff viewer (side-by-side), verify-chain button (green/red banner), export NDJSON.
- **`/admin/settings`** — clinic info, hours, public logo/doctor-photo upload (public assets only), discount caps, reminder templates (with live wa.me preview), print templates editor (sanitized textarea + live preview), display tokens per doctor (for TV), and session revocation controls.
- **`/reports/*`** — daily revenue, doctor share, syndicate balances; filters + CSV buttons; charts optional v1 (tables + big number cards are enough — keep it fast).

## 5. Step-by-step tasks

1. UI kit primitives + domain components + `/ui-catalog`.
2. Add the safe unauthenticated `/api/public/branding` projection (public asset URL only), then build the api client + auth store + route guards + login.
3. Secretary screens in order: board → calendar → patients → cashier → recalls → chat.
4. Doctor screens: today → exam → schedule → finance. Add a visible record-version conflict panel; never silently replace the server record.
5. Admin screens: users → pricing → syndicates → audit → settings → reports.
6. ⌘K palette + notification bell wiring.
7. i18n keys extracted as written (EN source; AR filled in 12 but files structured now).

## 6. Tests (vitest + Testing Library)

- Login → redirect per role; expired token → refresh retried once.
- Board: renders fixture entries; check-in mutation optimistic; SSE mock updates list.
- Exam: autosave debounce sends `record_version`; stale response shows a conflict panel; complete button calls endpoint then shows invoice toast.
- Cashier: pay modal validation (amount ≤ remaining); method grid.
- ⌘K: opens, queries, selects, navigates.
- Role guard: secretary hitting /admin/users sees 403 page.

## 7. Done-when checklist

- [ ] All §4 screens work against the real backend (no mocks)
- [ ] No hardcoded strings (i18n keys) and no hardcoded colors (tokens)
- [ ] Board, chat, bell update live via SSE without refresh
- [ ] Exam screen: history + form + Rx + attachments + print all on one screen, `Ctrl+S` saves
- [ ] Secretary can see attachment metadata but cannot download clinical file bytes
- [ ] Browser notifications contain operational text only, never patient clinical content
- [ ] Every destructive action confirms; every list has empty state
- [ ] vitest green; eslint clean

## 8. Gotchas

- SSE through Vite dev proxy: enable `ws`/streaming passthrough (configure proxy `changeOrigin`, no buffering).
- React strict-mode double-mount opens duplicate SSE connections — guard with refs.
- Keep bundle sane: route-level `lazy()` per feature; Radix imports per-package.
- Print routes open backend HTML (`/api/print/...`) in new tab with a short-lived,
  single-use `?print_token=` (60s) — implement the token endpoint in this
  phase. Never put JWTs or clinical file URLs in localStorage-readable URLs.
