# Phase 06 — Financial

**Revision 2.0:** financial mutations are idempotent and versioned, the
syndicate split has unambiguous names, and visit completion—not draft saving—
is the billing boundary.

**Goal:** money that a clinic can trust: price lists, syndicate/insurance
contracts with co-pay, **auto-invoice on visit completion**, discounts with
role caps, payments incl. Egyptian methods + partial payments/installments,
refunds, and the reports (daily revenue, doctor share, syndicate balances).

**Depends on:** 05 (visit completion hook). **Blocks:** 07 (invoice print).

---

## 1. Deliverables

- `services/pricing.py`: price resolution chain
- `services/billing.py`: auto-invoice, discounts, payments, refunds, statuses
- Syndicate CRUD + coverage/co-pay price lists (`syndicate_coverage` + `patient_share`)
- Reports API: daily revenue, per-doctor share, syndicate balances, payment-method mix
- Cashier UI spec (built in 09)

## 2. Rules (binding)

**M1 — Price resolution** (for a visit_type + doctor + patient):
1. If patient has `syndicate_id` and a `syndicate_price` exists for
   (syndicate, visit_type, doctor) or (syndicate, visit_type, null) →
   `syndicate_coverage` + patient share.
2. Else `price_list_item` for (visit_type, doctor).
3. Else (visit_type, null) clinic default.
4. Else `visit_type.default_price`.
Missing everywhere → invoice allowed with price 0 and a warning flag
(reception fixes before payment). **Per-hour doctors:** unit = hours, price =
`hourly_rate`; qty = `ceil(minutes/15)*0.25h` from the completed visit's
`started_at`/`ended_at` (minimum 1 unit of 15 min); visit_type price ignored
except as minimum charge if set.

**M2 — Auto-invoice.** `visit.complete` → create invoice (status `issued`)
with one item (the visit), resolved per M1. Syndicate patient: `total =
syndicate_coverage + patient_share`, `syndicate_due = syndicate_coverage`,
`patient_due = patient_share`. Cash patient: `patient_due = total`.
Idempotent: completing twice never duplicates (unique visit_id).

**M3 — Discounts.** On unpaid invoices only. `percent` (0–100) or `fixed`.
Caps: secretary ≤ `billing.discount_cap_secretary_pct` (default 10%); doctor ≤
100% on own invoices; admin unlimited. Over-cap → 403 with `DISCOUNT_CAP`.
Recomputed: `discount_total`, `total`, `patient_due` (discount applies to
patient share first; never reduces `syndicate_due`). A discount cannot reduce
patient due below zero; any requested excess is rejected rather than silently
changing the syndicate receivable.

**M4 — Payments.** Against `patient_due`. Multiple payments (installments)
until covered → status `issued → partially_paid → paid`. Method enum incl.
`cash, card, fawry, instapay, wallet, meeza`; optional `reference`. Overpayment
→ 409. Payment on `cancelled`/`refunded` → 409. Every payment/refund requires
an idempotency key and locks the invoice row.

**M5 — Immutability.** Once any payment exists: invoice items/discounts frozen;
edits only via admin "cancel + reissue" (creates linked new invoice, old one
`cancelled`, both audited). Refunds = `payment(is_refund=true)` rows, never
negative edits; `paid_total` is gross payments, `refunded_total` is gross
refunds, and `net_paid = paid_total - refunded_total`; full net refund → status
`refunded`.

**M6 — Syndicate balances.** Derived (not stored): per syndicate =
Σ `syndicate_due` on non-cancelled invoices − Σ recorded settlements. v1 has no
settlement entity — report shows accrued balance only (settlements = post-v1;
noted in report UI).

**M7 — Numbering.** `INV-{YYYY}-{seq:06d}` via `number_sequence(invoice, year)`.
Numbers never reused (cancelled invoices keep their number — ETA-friendly).

**M8 — Reports (all admin; doctor sees own only; secretary sees daily cashier).**
- Daily revenue: net payments (positive receipts minus refund rows) grouped by day/method (+ per-doctor split).
- Doctor share: per doctor per period: completed visits count, invoiced total,
  collected total. (Share % rules differ per clinic — v1 shows raw totals;
  percentage config is post-v1.)
- Syndicate balances (M6) + per-syndicate invoice list.
- All reports `?from&to&doctor_id` + CSV export.

## 3. API endpoints (`/api/*`)

| Method & path | Role | Purpose |
|---|---|---|
| `GET/PUT /api/pricing?doctor_id=` | admin | matrix editor (visit_type × doctor prices) |
| `GET/POST /api/syndicates` · `PATCH /api/syndicates/{id}` | admin | CRUD |
| `GET/PUT /api/syndicates/{id}/prices` | admin | syndicate coverage + patient-share price list editor |
| `GET /api/invoices?status&patient&doctor&from&to` | staff (scoped) | list |
| `GET /api/invoices/{id}` | staff | items, discounts, payments |
| `POST /api/invoices/manual` | secretary, admin | non-visit invoice (services/products free items) |
| `POST /api/invoices/{id}/items` · `DELETE` | secretary, admin | only while unpaid (M5); invoice `record_version` + idempotency key |
| `POST /api/invoices/{id}/discount` · `DELETE /api/discounts/{id}` | per M3 | invoice `record_version` + idempotency key |
| `POST /api/invoices/{id}/payments` | secretary, admin | `{amount, method, reference?}` + `Idempotency-Key` |
| `POST /api/payments/{id}/refund` | admin | `{amount?}` default full + `Idempotency-Key` |
| `POST /api/invoices/{id}/cancel-reissue` | admin | M5 flow |
| `GET /api/reports/daily-revenue?from&to` | per M8 | |
| `GET /api/reports/doctor-share?from&to&doctor_id` | per M8 | |
| `GET /api/reports/syndicate-balances` | admin | |
| All reports `&format=csv` | — | export |

## 4. Cashier UX spec (built in 09)

- `/cashier` default view: today's `issued`+`partially_paid` invoices ("to
  collect"), each row: patient chip, doctor, visit type, total, net paid, remaining,
  big **Pay** button → modal: amount (default remaining), method grid (6
  icons), reference field (shown for fawry/instapay), optional print receipt.
- Invoice drawer: items, discount add (shows cap hint per role), payments list,
  refund (admin), print invoice (phase 07).
- Syndicate patient invoices show split: "Syndicate covers X · Patient pays Y".
- Partial payment UX: remaining badge `--warning`; invoice list filter
  "unpaid this week".

## 5. Step-by-step tasks

1. `services/pricing.py` (M1) + tests incl. per-hour rounding and the explicit `syndicate_coverage` split.
2. `services/billing.py`: auto_invoice (M2, idempotent), discount (M3),
   payment (M4), refund/cancel-reissue (M5), numbering (M7).
3. Wire `visit.complete` hook from phase 05 to `auto_invoice`.
4. Syndicate + pricing routes; invoice/payment routes.
5. Reports (SQL group-bys) + CSV.
6. Seed: one syndicate "نقابة المعلمين" (teachers) with coverage/co-pay prices
   (consult 200 covered + 50 patient share), one cash visit type set.
7. Tests (§6).

## 6. Tests

- M1 chain: each fallback level; syndicate doctor-specific beats syndicate generic; total equals coverage + patient share.
- Per-hour: 40 min → 0.75h × rate; minimum-charge visit type respected.
- Auto-invoice idempotent on double-complete.
- Discount: secretary 15% → 403; secretary 10% → ok; totals recomputed; syndicate_due untouched.
- Installments: 3 payments → statuses issued→partially_paid→paid; overpay → 409.
- Immutability: add item after payment → 409; cancel-reissue produces linked pair with correct numbers.
- Refund: full → status refunded; `net_paid = paid_total - refunded_total`.
- Idempotency: retrying a payment/refund returns the original result; same key with changed amount/method → 409.
- Stale invoice `record_version` on an item/discount mutation → 409 with no financial change.
- Reports: seeded day → daily revenue sums match payments; CSV parses; syndicate balance = Σ syndicate_due.
- Audit events for discount/payment/refund/cancel-reissue with before/after totals.

## 7. Done-when checklist

- [ ] Visit complete → invoice exists with correct price in ≤1 extra query round trip
- [ ] Syndicate co-pay split shows on invoice payload
- [ ] M1–M8 test-covered
- [ ] Reports match hand-computed fixtures
- [ ] Audit chain green after full billing day simulation
- [ ] Replaying a browser/network request cannot double-charge an invoice

## 8. Gotchas

- Always `Decimal`, quantize 2dp at boundaries; SQLite stores Numeric as TEXT-ish — compare via SQLAlchemy, not raw SQL floats.
- Timezone: "daily" buckets by clinic-local date, not UTC.
- A payment and a discount racing: lock invoice row (`SELECT FOR UPDATE`) during any mutation.
- Manual invoices have `visit_id=null` — reports must include them in revenue but not in doctor visit counts.
- Do not treat `syndicate_due` as money already collected; it is an accrued receivable until a future settlement workflow exists.
