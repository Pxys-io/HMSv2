# web-public — HMSv2 patient-facing site

Separately deployable landing + booking + account app. Talks only to
`/api/public/*`.

- Dev: `npm run dev` (port 5174, proxies `/api` → `http://localhost:8000`)
- Lint: `npm run lint` · Test: `npm test` · Build: `npm run build`
- Design tokens: `src/styles/tokens.css` (Plan/00)
