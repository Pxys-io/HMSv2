# Phase 05 — EMR (Electronic Medical Record)

**Revision 2.0:** clinical writes are versioned, clinical reads are access
audited, and uploaded files remain quarantined until scanned. The PWA improves
capture speed but does not create an offline clinical copy.

**Goal:** the doctor's world: start a visit from the queue, record everything
(all optional), see a bird's-eye timeline of past visits, attach photos of
labs/imaging (incl. phone camera via PWA), prescribe from the drug DB, and mark
follow-ups.

**Depends on:** 04. **Blocks:** 06 (invoice auto-creation on visit completion),
07 (printables need prescriptions; recalls need follow_up_due).

---

## 1. Deliverables

- `services/visits.py`: create (from queue), update (auto-save friendly), complete
- Diagnoses (differential/final) sub-resource
- Medication DB CRUD + search; prescription create/update
- Attachment upload pipeline (images re-encoded; PDFs validated and scanned), thumbnails, authenticated file serving
- Patient timeline endpoint (non-null projection)
- Follow-up fields + hooks for recall (07)

## 2. Rules (binding)

**E1 — Everything optional.** A visit may be completed with zero clinical data.
Validation only enforces types/lengths, never presence.

**E2 — Ownership.** Doctors see/edit their own visits fully; other doctors in
the clinic can read shared clinical visits (small clinic, shared care), but
cannot edit another doctor's signed record. Secretary sees demographics and
attachment metadata only (no clinical text or file bytes). Admin reads all;
every clinical read/file download is access-audited. `notes_private` = author
doctor only.

**E3 — Visit lifecycle.** Created `open` (at queue `start`) → editable while
open → `complete` sets `ended_at`, queue `completed`, and appointment
`completed` if linked → triggers invoice auto-creation (phase 06 hook) →
completed visits are editable by the same doctor for 24h only with an expected
`record_version` (audited), then read-only (admin correction workflow, audited).

**E4 — Timeline projection.** `GET /api/patients/{id}/timeline` returns visits
desc by date, each as: id, date, doctor name, visit type, plus **only non-null
fields** among {chief_complaint, vitals, findings, labs, imaging, diagnoses
(final first), plan, notes_next_visit, attachments count, has_rx}. The client
renders cards; expand → full visit. `notes_next_visit` of the *previous* visit
also surfaces as a banner when opening a new exam.

**E5 — Attachments.**
- Accept: JPEG/PNG/WebP/HEIC-as-JPEG (client converts), PDF. Max 15MB.
- Images: EXIF stripped, re-encoded (quality 85, max edge 2048px), thumbnail
  320px. Stored `UPLOAD_DIR/patient_{profile_id}/{yyyy}/{mm}/{uuid}.jpg` (+`_thumb.jpg`). PDFs stored as-is.
- Uploads enter `pending` quarantine. Images are re-encoded; PDFs are
  MIME-sniffed, parsed for a valid structure, scanned by ClamAV in production,
  and remain unavailable until `scan_status=clean`. Rejected files are deleted
  after an audit event.
- Serving: `GET /api/files/{attachment_id}` streams with doctor/admin clinical
  authorization and an `access` audit event. No direct static exposure.
  `Content-Disposition: inline` only after a clean scan; response headers are
  `Cache-Control: private, no-store`.
- Delete: author doctor or admin; physical file removed; audit row kept. A
  secretary can see metadata but cannot download or delete clinical files.

**E6 — Prescription.** One per visit. Items from `medication` DB (search-as-
you-type) or free-text. Print uses template `rx` (phase 07). Editing allowed
while visit editable (E3).

**E7 — Follow-up.** Setting `follow_up_weeks` computes `follow_up_due =
visit date + N weeks` (editable date). Recall list (phase 07) reads this.

## 3. API endpoints (`/api/*`)

| Method & path | Role | Purpose |
|---|---|---|
| `POST /api/visits` | doctor | `{queue_entry_id}` or `{patient_profile_id, visit_type_id}` (adhoc) + `Idempotency-Key` → creates open visit |
| `GET /api/visits/{id}` | per E2 | full visit incl. diagnoses, Rx, attachments |
| `PATCH /api/visits/{id}` | author doctor | partial update + required `record_version` + `Idempotency-Key`; autosave target |
| `PUT /api/visits/{id}/diagnoses` | author doctor | replace full list + `record_version` + `Idempotency-Key` `[{kind,label,icd10_code?,notes?}]` |
| `POST /api/visits/{id}/complete` | author doctor | ends visit + `Idempotency-Key`; fires billing hook |
| `POST /api/visits/{id}/reopen` | author doctor (≤24h), admin | back to open (audited) |
| `GET /api/patients/{id}/timeline` | per E2 | E4 projection |
| `GET /api/patients/{id}` | staff | profile + alerts + counts |
| `PATCH /api/patients/{id}/demographics` | secretary, doctor, admin | demographics only (audited) |
| `PATCH /api/patients/{id}/clinical-alerts` | doctor, admin | allergies/chronic conditions (audited clinical write) |
| `GET /api/medications?q=` | staff | search (name/ar/form), top 20 |
| `POST /api/medications` · `PATCH /api/medications/{id}` | doctor, admin | drug DB manage |
| `GET /api/visits/{id}/prescription` · `PUT /api/visits/{id}/prescription` | author doctor | get/replace Rx + items; write requires visit `record_version` + `Idempotency-Key` |
| `POST /api/visits/{id}/attachments` | doctor, admin | multipart upload + `Idempotency-Key` (also `/api/patients/{id}/attachments`) |
| `GET /api/files/{id}` | doctor, admin | stream clean file/thumb (`?thumb=1`) + access audit |
| `DELETE /api/attachments/{id}` | author doctor, admin | E5 |

Autosave contract: `PATCH` accepts any subset plus required `record_version`;
returns the saved visit and incremented version. A stale version returns `409
RECORD_CONFLICT` with the server copy and changed fields. The client debounces
800ms, never silently overwrites, and shows `Saved HH:MM:SS` only after the
server acknowledges the version.

## 4. Exam screen UX spec (built in 09; contracts here)

Layout per Plan/00 §5.2. Behavior requirements:

- Open from queue `start` → visit exists by the time screen renders.
- **Left timeline:** cards per E4; sticky "New visit" banner shows previous
  `notes_next_visit` if any. Cards lazy-render (max 20, scroll-load more).
- **Center form sections (collapsible, state persisted per doctor):**
  Complaint · History · Vitals (6 mini-inputs) · Exam · Findings · Labs ·
  Imaging · Diagnoses (two lists: DD, Final — quick-add chips from recent
  labels) · Plan · Notes next visit · Private notes · Follow-up (N weeks ↔ date).
- **Right rail:** Rx builder (med search → item rows dose/freq/duration →
  drag order), Attachments (upload button, camera button on mobile per Plan/10,
  thumb grid, kind picker), Print menu (Rx/report/sick-leave/referral — phase
  07), Save state indicator, Complete & invoice button.
- Keyboard: `Ctrl+S` save, `Ctrl+Enter` complete, `/` focuses timeline search.
- Unsaved-guard on route leave (autosave makes it rare).

## 5. Step-by-step tasks

1. Schemas: visit (full/patch/timeline), diagnosis, medication, prescription, attachment.
2. `services/visits.py` (E1–E4, E7) + `services/medications.py` + `services/attachments.py` (E5) with Pillow pipeline, MIME sniffing, quarantine, ClamAV adapter, and access-audit calls. Enqueue `outbox_event(kind=attachment_scan)` and let the restart-safe worker mark clean/rejected.
3. Routes §3; file streaming with correct mime + clinical authorization; every clinical read/download calls the audit access service.
4. Hook: `queue.start` → create visit (idempotent — re-enter returns existing open visit).
5. Hook stub: `visit.complete` → `billing.auto_invoice(visit)` (real impl in 06; here a no-op service function with the final signature, so phases decouple).
6. Seed: 30 common Egyptian medications (Augmentin 1g, Panadol Extra, Cataflam 50, Flagyl 500, Nexium 40, Zithromax 500, Brufen 400, Ventolin inh, Insulin Mixtard 30, Glucophage 850, Concor 5, Amaryl 2, Plavix 75, Aspirin 81, Ciprocin 500, Vibramycin 100, Histop, Zyrtec 10, Diclac 75 gel, Voltaren inj, Dexamethasone 8, Rocephin 1g, Flagyl gel, Canesten cream, Fucidin cream, Betnovate cream, E-Mox 500, Maalox plus, Spasmocan, Cetal drops) with Arabic names where standard.
7. Tests (§6).

## 6. Tests

- Complete an empty visit → ok; queue/appointment transitions and invoice hook are called with visit id.
- E2 matrix: secretary reads visit → clinical fields absent in response and file bytes forbidden; other doctor reads → present except `notes_private`; patient token → 403 on all.
- Timeline projection: visit with only plan+diagnosis → card has exactly those keys (no nulls).
- 24h edit window: freeze clock +25h → PATCH 409; admin reopen → PATCH ok.
- Attachments: upload 5MB PNG → pending then clean + thumb exists + EXIF gone (check no EXIF tags); 20MB → 413; `.exe` → 415; invalid/infected PDF → rejected; file endpoint requires doctor/admin auth; `?thumb=1` returns thumb only after clean.
- Clinical PATCH with a stale `record_version` → 409 and no changed fields.
- Prescription replace is atomic (items count matches; order preserved).
- Follow-up: weeks → due date; recall-feed query returns profile when due ≤ today+7 and no future appointment (feed itself built in 07 — test the query helper here).

## 7. Done-when checklist

- [ ] Queue start → exam screen data loads with one round trip (visit + timeline + Rx)
- [ ] Autosave PATCH works field-by-field; saved indicator data present
- [ ] Camera-sized phone photo (12MP) uploads, compresses, thumbnails correctly
- [ ] E1–E7 test-covered
- [ ] Audit rows for visit create/update/complete/attachment delete
- [ ] Stale `record_version` cannot overwrite a doctor's newer edit
- [ ] Clinical access/download events and unresolved audit intents verify correctly

## 8. Gotchas

- HEIC: browsers can't display it; iOS Safari converts to JPEG on `<input type=file capture>` automatically — document this; reject `image/heic` server-side with a clear message.
- Pillow must be compiled with libjpeg — use the official wheel (it is).
- Timeline with hundreds of visits: index on (patient_profile_id, created_at desc); page size 20.
- Never trust uploaded mime — inspect signatures with Pillow/python-magic, scan PDFs in production, and never serve a pending/rejected file.
- Do not offer a patient-upload endpoint in v1; the public account has no medical-file access.
