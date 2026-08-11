# Phase 10 — PWA & Mobile Doctor Experience

**Revision 2.0:** the PWA is installable and camera-friendly, but it does not
cache or queue clinical data. Offline support is deliberately limited to the
app shell to avoid leaving medical records on a shared phone.

**Goal:** make `web-staff` installable and phone-excellent for doctors: camera
capture of labs/imaging, fast mobile exam layout, sensible offline behavior.

**Depends on:** 09. **Blocks:** none (11–13 proceed in parallel order).

---

## 1. Deliverables

- PWA manifest + icons + service worker (vite-plugin-pwa)
- Camera capture flow for attachments
- Mobile layouts for doctor-critical screens (today queue, exam, timeline)
- Performance pass against budgets (§5)

## 2. Rules

**PWA1 — Install.** `manifest.webmanifest`: clinic name (from branding),
`display: standalone`, theme `#0D9488`, background `#F8FAFC`, icons 192/512 +
maskable. iOS: `apple-touch-icon`, `apple-mobile-web-app-capable`. "Add to home
screen" hint shown once to doctors on mobile (dismissible, per-user flag).

**PWA2 — Service worker.** `vite-plugin-pwa` with `generateSW`:
- Precache app shell.
- Runtime cache only versioned static assets, self-hosted fonts, and non-sensitive
  public branding assets. **Never cache any API response containing patients,
  visits, queues, invoices, attachments, auth, or staff data.**
- Never cache mutations, SSE, print pages, or public booking/account responses.
- Versioned cache names; `skipWaiting` + `clientsClaim` on new build, with a
  toast "new version — refresh" instead of silent swap.

**PWA3 — Offline truth.** This is a clinic tool: **offline = app shell only**.
The app shows an "offline — reconnecting" banner, but patient/visit screens do
not render stale cached clinical data. All clinical and queue queries require a
live API response; all mutations are disabled offline. No mutation queue or
background sync is built in v1. SSE reconnects automatically on regain.

**PWA4 — Camera capture.**
- Primary: `<input type="file" accept="image/*" capture="environment">` —
  native camera on iOS/Android, gallery fallback. HEIC handled per Plan/05 §8.
- Enhancement (if time): in-app camera via `getUserMedia` with resolution
  picker; otherwise ship the input flow only.
- After capture: client-side downscale to ≤2048px (canvas) before upload →
  fast on clinic Wi-Fi. Multi-shot: "add another" loop attaches all to the
  same visit; kind picker (lab/imaging/report/photo) per batch.

**PWA5 — Mobile exam layout.** Below `lg`: exam screen becomes tabbed —
**[History] [Exam] [Rx & Files]** — same components, same data; patient strip
sticky on top; save state always visible. Queue "call next" is a thumb-reach
FAB on `/today` mobile.

**PWA6 — Doctor speed budgets.** See §5.

## 3. Step-by-step tasks

1. vite-plugin-pwa config + manifest + icons (generate from a source SVG via `sharp` script or pwa-assets-generator).
2. SW runtime caching rules per PWA2 + update toast.
3. Offline banner + mutation gating (`navigator.onLine`); do not add Background Sync.
4. Camera capture component + client downscale + batch upload to phase-05 endpoints.
5. Mobile layouts (PWA5) + FAB.
6. Lighthouse CI pass (local): fix until budgets met.
7. Tests (§4) + manual device checklist (§6).

## 4. Tests

- Manifest valid (name, icons, maskable).
- SW precaches shell and public assets; DevTools verifies no patient/visit/queue/invoice/file API response enters any cache.
- Downscale: 12MP photo → ≤2048px edge, ≤1.5MB JPEG before upload.
- Capture component renders on iOS Safari + Chrome Android (manual, §6).
- Offline: clinical screen shows no cached patient data; save and queue actions disabled.

## 5. Performance budgets (doctor path, mid-range Android, clinic Wi-Fi)

| Metric | Budget |
|---|---|
| Login → today queue interactive | ≤ 3s |
| Open exam (visit+timeline+Rx) | ≤ 2s |
| Autosave round trip | ≤ 500ms |
| Photo capture → uploaded | ≤ 4s (post-downscale) |
| Lighthouse PWA | installable, ≥ 90 performance on key routes |
| JS bundle (initial, gzip) | ≤ 350KB staff app |

## 6. Manual device checklist

- [ ] iPhone Safari: install, camera capture (HEIC), exam tabs usable one-handed
- [ ] Android Chrome: install prompt, capture, FAB reach
- [ ] Offline toggle: banner + no clinical data rendering + disabled mutations
- [ ] New version toast appears after deploy

## 7. Done-when checklist

- [ ] PWA installable on both platforms; icon + name correct
- [ ] PWA1–PWA6 verified; budgets in §5 met or exception documented
- [ ] Photo from phone lands in visit attachments with thumbnail
- [ ] No SW caching of any patient/visit/queue/invoice/file/auth/mutating/SSE request (audited in DevTools)

## 8. Gotchas

- iOS camera input ignores `capture` nuances per version — always offer gallery too.
- Canvas downscale must handle EXIF orientation (use `createImageBitmap` with `imageOrientation: "from-image"` or a tiny util).
- SW + authenticated file URLs: do not cache them at all. A shared or borrowed
  phone must not retain clinical files after the browser tab closes.
- Keep the staff app a PWA, but `web-public` stays a plain site (SEO > installability there).
