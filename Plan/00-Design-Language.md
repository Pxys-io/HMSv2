# 00 — Design Language (binding for every UI in HMSv2)

**Revision 2.0:** the visual language is unchanged in spirit, but clinical
privacy, state labels, and safe interaction feedback are now explicit.

Applies to `web-staff`, `web-public`, print output, and emails. Any new screen
MUST use the tokens and components defined here. If a screen needs something
new, add it here first, then build it.

Two personalities, one system:

- **Staff app** = a *tool*: dense, fast, keyboard-first, quiet visuals, zero decoration.
- **Public site** = *marketing + trust*: spacious, warm, photographic, big type.
  Same tokens, looser density.

---

## 1. Brand

| Token | Value | Notes |
|---|---|---|
| Product name | HMSv2 (internal) | Public brand = clinic's own name, from `setting.clinic.*` |
| Voice (EN) | Clear, short, professional. No jargon in patient UI. | |
| Voice (AR) | Modern Standard Arabic with Egyptian-friendly phrasing; reception templates may be Egyptian colloquial. | Button: "احجز موعد" not "إجراء حجز" |
| Logo | Clinic logo uploaded in settings; fallback = clinic initial in a rounded square | |

## 2. Color

Base scale: Tailwind slate (neutrals) + teal (brand). All colors via CSS
variables so a clinic can rebrand later. v1 ships defaults only.

### 2.1 Core palette (light theme, v1 default)

| Token | Hex | Usage |
|---|---|---|
| `--brand-600` | `#0D9488` | primary buttons, links, active states |
| `--brand-700` | `#0F766E` | hover on primary |
| `--brand-50` | `#F0FDFA` | selected rows, soft highlights |
| `--ink-900` | `#0F172A` | headings (slate-900) |
| `--ink-600` | `#475569` | body text (slate-600) |
| `--ink-400` | `#94A3B8` | placeholders, disabled |
| `--bg` | `#F8FAFC` | app background (slate-50) |
| `--surface` | `#FFFFFF` | cards, panels |
| `--border` | `#E2E8F0` | hairlines (slate-200) |

### 2.2 Semantic

| Token | Hex | Usage |
|---|---|---|
| `--success` | `#16A34A` | paid, completed, available |
| `--warning` | `#D97706` | waiting too long, partial payment, follow-up due |
| `--danger` | `#DC2626` | cancelled, no-show, destructive actions |
| `--info` | `#2563EB` | checked-in, informational |

### 2.3 Status colors (appointments/queue — identical everywhere)

| Status | Badge bg | Badge text |
|---|---|---|
| Booked | `#F1F5F9` | `#475569` |
| Checked-in / Arrived | `#DBEAFE` | `#1D4ED8` |
| Called | `#E0E7FF` | `#4338CA` |
| Waiting > 20 min | `#FEF3C7` | `#B45309` |
| In room | `#D1FAE5` | `#047857` |
| Completed | `#CCFBF1` | `#0F766E` |
| Cancelled | `#FEE2E2` | `#B91C1C` |
| No-show | `#FFEDD5` | `#C2410C` |

### 2.4 Dark mode

v1 ships **light only**, but components must reference semantic Tailwind classes
(`bg-surface`, `text-ink-600`) mapped to CSS variables — never hardcode hex — so
dark mode is a variable swap later.

## 3. Typography

| Role | Font | Fallback |
|---|---|---|
| Latin UI | **Inter** | system-ui |
| Arabic UI | **IBM Plex Sans Arabic** | Tahoma |
| Monospace (codes, refs, invoice numbers) | **IBM Plex Mono** | monospace |

Self-host via `@fontsource/*` packages (no external CDN — clinic must work offline).

### Scale (16px base)

| Token | Size | Weight | Use |
|---|---|---|---|
| `display` | 2.25–3rem | 700 | public site hero only |
| `h1` | 1.5rem | 700 | page titles |
| `h2` | 1.25rem | 600 | section titles |
| `h3` | 1.0625rem | 600 | card titles |
| `body` | 0.9375rem (staff) / 1rem (public) | 400 | default |
| `small` | 0.8125rem | 400 | meta, secondary table text |
| `tiny` | 0.75rem | 500 | badges, captions |

Rules:

- **Western numerals (0-9) everywhere**, including Arabic UI (Egyptian medical norm). `font-variant-numeric: tabular-nums` for times, queue numbers, money.
- Arabic line-height ×1.15 vs Latin.
- Doctor-facing screens: compact density (line-height 1.35).

## 4. Spacing, radius, elevation

- 4px base grid; spacing steps 4 / 8 / 12 / 16 / 24 / 32 / 48.
- Radius: 6px inputs & badges · 10px cards · 16px modals · pill 999px.
- Elevation: `e0` flat with hairline border (staff default) · `e1` `0 1px 2px rgb(15 23 42/.06)` dropdowns · `e2` `0 8px 24px rgb(15 23 42/.12)` modals.
- Staff app prefers **borders over shadows**. Public site may use soft shadows.

## 5. Layout shells

### 5.1 Staff app shell

```
+----------------------------------------------------------+
| topbar 56px: logo . page title . ⌘K . lang . bell . user  |
+----------+-----------------------------------------------+
| sidebar  |  content (max-width 1440px, padding 24)       |
| 232px    |                                               |
| by role  |                                               |
+----------+-----------------------------------------------+
```

- Sidebar collapsible to 56px icon rail (persisted per user). Off-canvas drawer below `lg`.
- ⌘K always visible in topbar, placeholder: "بحث سريع… / Quick search… ⌘K".
- Doctor exam screen is full-bleed (no content max-width).
- Breakpoints: sm 640 · md 768 · lg 1024 · xl 1280.

### 5.2 Doctor exam shell — the most important screen in the system

```
+----------------------------------------------------------+
| patient strip: name . P-code . age . phone . alerts . no-show count |
+-----------+-------------------------------+--------------+
| history   | CURRENT VISIT (form)          | actions      |
| timeline  | every field optional          | Rx builder   |
| cards     |                               | attachments  |
| (non-null)|                               | print . save |
| 300px     | flexible                      | 320px        |
+-----------+-------------------------------+--------------+
```

- Side panels collapsible; save = `Ctrl+S`; everything reachable by keyboard.
- This layout is sacred: one screen = history + exam + prescription + attachments + print.
- Clinical data is never rendered in a public-site component, email body, TV
  display, browser notification, or service-worker cache.
- A clinical save shows `Saving…`, `Saved at HH:MM`, or `Conflict — review`; it
  must never imply a successful save before the server acknowledges the record
  version.

### 5.3 Public site shell

Marketing header (logo, nav, language switch, "احجز الآن / Book now" CTA),
content sections, footer (hours, address, phones, legal). Booking flow lives
under `/book/*` with a slim header (logo + step indicator) — no distractions.

## 6. Component inventory

Build once in `web-staff/src/components/ui/`; `web-public` gets its own trimmed
copy (it must stay independently deployable — **no shared packages between the
two apps**, shared only by copy-paste from this spec).

### 6.1 Primitives (Radix + Tailwind wrappers)

Button (`primary|secondary|ghost|danger|outline`, sizes `sm|md|lg|icon`),
Input, Textarea, Select, Combobox (async), Checkbox, Radio, Switch, DatePicker,
TimePicker, Dialog (confirm variant), Popover, DropdownMenu, Tabs, Tooltip,
Badge (status-aware per §2.3), Card, Table (dense variant), Skeleton, Empty
state, Avatar, Toast (sonner), Sheet (side drawer), Separator, ScrollArea.

### 6.2 Domain components

| Component | Purpose | Key props |
|---|---|---|
| `PatientChip` | inline patient identity | profile, shows code+name+age |
| `PatientSearchBox` | combobox hitting `/api/search/patients` | onSelect |
| `StatusBadge` | appointment/queue/invoice status | status |
| `QueueNumber` | big mono queue ticket | seq, waitMin |
| `WaitTimer` | live mm:ss since check-in, amber >20m | since |
| `VisitTimelineCard` | one past visit, non-null fields only | visit |
| `MoneyText` | formatted EGP, tabular-nums | amount |
| `PhoneLink` / `WhatsAppLink` | tel: / wa.me actions | phone, message? |
| `FileThumb` | attachment thumbnail + lightbox | attachment |
| `CommandPalette` | ⌘K global search | — |
| `NotificationBell` | SSE-driven unread badge | — |
| `PrintButton` | opens printable route in new tab | docType, ids |
| `DoctorPicker` / `VisitTypePicker` | selects fed from API | — |
| `ScheduleGrid` | week grid of shifts | doctorId |
| `DayBoard` | waiting-room board (phase 04) | doctorId, date |

### 6.3 Empty/error conventions

- Empty states: one-line icon + sentence + primary action button. Never a blank table.
- Errors: toast for transient; inline red text under field for validation; full-page error only for route-level failures with a "retry" button.

## 7. Iconography

`lucide-react` only. 16px in dense UI, 20px default, 24px in empty states.
Directional icons (arrows, chevrons, "back") must mirror in RTL — wrap in a
`DirIcon` helper that flips `scaleX` under `[dir="rtl"]`. Non-directional icons
(clock, phone, printer) never flip.

## 8. Motion

- Micro-interactions 120–180ms, `ease-out`. Panel/drawer 200ms.
- Board/SSE updates: 150ms fade; queue position change: 250ms slide.
- Respect `prefers-reduced-motion`: disable all non-essential animation.
- No bounce/spring physics in staff app; subtle spring allowed on public site hero.

## 9. RTL rules (details in Plan/12, summarized here)

- `<html dir>` flips per locale; use CSS **logical properties** only (`ms-`, `me-`, `ps-`, `pe-`, `start-`, `text-start`…). Physical `ml/mr/pl/pr/left/right` are forbidden in components.
- Phone numbers, codes, amounts always LTR islands: `<bdi dir="ltr">`.
- Forms mirror; tables mirror; timeline rail mirrors.
- Keyboard: `Tab` order follows visual order automatically; verify per screen.

### 9.1 Data-class styling rules

- **Operational:** appointments, queue state, and payment status. These may
  appear on reception boards and short-lived staff notifications.
- **Clinical:** complaints, findings, diagnoses, prescriptions, labs, imaging,
  and attachments. Staff-only; never in browser notifications or email. Full
  content opens only after an explicit staff action.
- **Public:** clinic branding, services, doctors, hours, and location. These
  may be cached and indexed.
- Patient names never appear on the TV display; it shows a queue number and
  first name only when the clinic explicitly enables that privacy mode.

## 10. Print design system (phase 07 uses this)

| Document | Size | Margins | Notes |
|---|---|---|---|
| Prescription (روشتة) | A5 portrait | 12mm | Letterhead top, patient line, Rx items table, signature block bottom-right (bottom-left in AR stays right — RTL doc) |
| Medical report / sick leave / referral | A4 portrait | 18mm | Letterhead, title, body, signature |
| Invoice/receipt | A5 portrait | 12mm | Number, items, totals, payments, remaining |

- Letterhead from settings: logo, clinic name (AR+EN), address, phones.
- Print routes are standalone pages (`/print/...`) with `@media print` CSS, system fonts fallback, **white background only**, no app chrome.
- A "Print" opens the route in a new tab and auto-calls `window.print()`.
- Sick-leave, referral, and medical-report composition is doctor/admin only;
  reception can print a completed prescription or invoice but cannot compose
  clinical text or download raw clinical attachments. Print pages make no
  external requests.

## 11. Email design

Plain responsive HTML emails, single column, brand header (clinic name),
max-width 560px, one CTA button (`--brand-600`), footer with address/phones.
AR and EN templates. No diagnoses, prescription details, lab results, or other
clinical content in email. No images except optional logo URL.

## 12. Accessibility floor

- WCAG AA contrast for all text; focus rings visible (`2px` brand outline, offset 2px).
- All interactive elements keyboard-operable; modals trap focus.
- Touch targets ≥ 36px on mobile (44px on public site).
- `aria-label` on icon-only buttons; live region for queue-board changes.

## 13. Performance aesthetic

Speed *is* a design feature here (the doctor asked for fast):

- First interaction on any staff screen < 100ms after data; skeletons for >300ms loads; never spinners for full pages.
- Optimistic updates are allowed for queue position/status and chat send only;
  appointment, payment, and clinical-record mutations wait for server
  acknowledgement and show a conflict/error state when the idempotency key or
  record version is rejected.
- Budgets in Plan/10 §Performance.

## 14. Copy micro-spec (selected, binding)

| Context | EN | AR |
|---|---|---|
| Book CTA | Book now | احجز الآن |
| Check-in | Check in | تسجيل وصول |
| Call next | Call next | النداء على التالي |
| Waiting room | Waiting room | منطقة الانتظار |
| No-show | No-show | لم يحضر |
| Follow-up due | Follow-up due | موعد المتابعة مستحق |
| Syndicate/insurance | Insurance / syndicate | نقابة / تأمين |
| Co-pay | Patient share | حصة المريض |
| Walk-in | Walk-in | بدون حجز |
