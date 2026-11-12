# PaceForge frontend

Angular single-page app (standalone components, signals, zoneless). It talks to the Django API
under `/api` on the same origin; during development `ng serve` proxies `/api` to
`http://localhost:8000` (see `proxy.conf.json`).

```
npm ci            # install dependencies
npm start         # dev server on http://localhost:4200 (start the Django backend first)
npm test          # unit tests (Vitest); add -- --no-watch for a single run
npm run build     # production build into dist/
```
