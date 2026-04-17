# tutor-platform-web

Vue 3 single-page application for TMRP (Tutor Matching and Rating Platform). Ships as a Vite-built static bundle served by Nginx in production.

For the project overview, see the [root README](../README.md).

---

## Table of Contents

- [What This App Does](#what-this-app-does)
- [Requirements](#requirements)
- [Getting Started](#getting-started)
- [Scripts](#scripts)
- [Environment Variables](#environment-variables)
- [Code Layout](#code-layout)
- [Routes and Role Guards](#routes-and-role-guards)
- [State Management](#state-management)
- [API Layer](#api-layer)
- [Build Output and Nginx](#build-output-and-nginx)
- [Troubleshooting](#troubleshooting)

---

## What This App Does

The frontend is a role-aware SPA with three distinct experiences:

- **Parent** — search tutors, chat, send match invitations, manage children, track lesson notes / exam scores / expenses.
- **Tutor** — manage profile & visibility, respond to invitations, record lessons, log exams, review earnings.
- **Admin** — user list, CSV import/export, seed data generation, background task monitoring.

All data flows through `/api/*` REST calls to the FastAPI backend. There's no direct database access; every business rule is enforced server-side.

---

## Requirements

| Tool | Version |
|------|---------|
| Node.js | 18+ |
| npm | 9+ (bundled with Node 18) |

A running backend at `http://localhost:8000` (or wherever `VITE_API_BASE_URL` points).

---

## Getting Started

```bash
cd tutor-platform-web
npm install
npm run dev
```

Dev server starts on <http://localhost:5273> (port configured in `vite.config.js`).

For first-time setup alongside the backend, use `tutor-platform-api/start.bat` (Windows) or `docker compose up` from the repo root — both bring up the API, worker, database, and frontend together.

---

## Scripts

| Script | What it does |
|--------|--------------|
| `npm run dev` | Vite dev server with HMR on port 5273 |
| `npm run lint` | Runs `scripts/check-no-v-html.mjs` to fail the build if `v-html` creeps into a template (XSS guard) |
| `npm run build` | Production build into `dist/`. Auto-runs `lint` first via `prebuild`. |
| `npm run preview` | Serve the production build locally (sanity check before deploy) |

---

## Environment Variables

Vite only exposes variables prefixed with `VITE_`. Set them in a `.env` file or pass them to `vite build`.

| Variable | Default | Purpose |
|----------|---------|---------|
| `VITE_API_BASE_URL` | `""` | Base URL prepended to axios requests. Both `.env.development` and `.env.production` ship with an empty value. Override with a full origin only when the API is at a different host; `.env.example` shows `http://localhost:8000` as a reference for that scenario. |

### The empty-baseURL pattern

Both dev mode and Docker production use `VITE_API_BASE_URL=""`. The routing layer is different in each case:

- **Dev (`npm run dev`)**: `.env.development` sets `VITE_API_BASE_URL=""`. The Vite dev server's built-in proxy (configured in `vite.config.js`) forwards every `/api/*` request to `http://localhost:8000`, keeping cookies same-origin.
- **Docker production**: `docker-compose.yml` passes `VITE_API_BASE_URL=""` as a build arg. The browser sends relative paths which Nginx inside the web container proxies to `api:8000`.

In both cases every frontend API call already includes the `/api/` prefix (e.g. `axios.post('/api/auth/login', ...)`), so an empty base URL produces the correct relative path.

**Do not** change this to `/api` (you'd get `/api/api/...`) or to `http://api:8000` (the browser can't resolve container hostnames). The rationale is documented in `src/api/baseURL.js` and `nginx.conf`.

---

## Code Layout

```
tutor-platform-web/
├── Dockerfile                  # Multi-stage: Vite build → nginx-unprivileged static serve
├── nginx.conf                  # /api/* → api:8000, SPA fallback, asset caching,
│                               # edge rate limit (20 r/s, burst 40), global security headers + CSP
├── vite.config.js              # Port 5273, @ alias, dev proxy (/api → localhost:8000), vendor/charts manual chunks, sourcemap off
├── index.html
├── package.json
├── scripts/
│   └── check-no-v-html.mjs     # Pre-build lint: fail if any template uses v-html
└── src/
    ├── main.js                 # App bootstrap: Pinia, router, global styles
    ├── App.vue
    ├── constants.js            # Shared enums (roles, match status values, labels, ...)
    ├── style.css               # Tailwind entry
    │
    ├── router/
    │   └── index.js            # Route table, role-based navigation guards
    │
    ├── stores/                 # Pinia stores
    │   ├── auth.js             # JWT, current user, role, login/logout, refresh
    │   ├── tutor.js            # Tutor search filters, results, profile cache
    │   ├── match.js            # Match list, status transitions
    │   ├── message.js          # Conversations, unread counts
    │   └── toast.js            # Global toast notifications
    │
    ├── api/                    # Axios service layer (one file per resource)
    │   ├── index.js            # Axios instance: baseURL, auth interceptor, error mapping
    │   ├── baseURL.js          # API_BASE_URL resolver (see Environment Variables)
    │   ├── authHandler.js      # Shared 401 / refresh-token handler reused by the interceptor
    │   ├── auth.js
    │   ├── tutors.js
    │   ├── students.js
    │   ├── subjects.js
    │   ├── matches.js
    │   ├── sessions.js
    │   ├── exams.js
    │   ├── reviews.js
    │   ├── messages.js
    │   ├── stats.js
    │   └── admin.js
    │
    ├── views/                  # Page-level components (mapped by router)
    │   ├── LoginView.vue
    │   ├── RegisterView.vue
    │   ├── parent/
    │   │   ├── DashboardView.vue
    │   │   ├── SearchView.vue
    │   │   ├── TutorDetailView.vue
    │   │   ├── MatchDetailView.vue
    │   │   ├── StudentsView.vue
    │   │   └── ExpenseView.vue
    │   ├── tutor/
    │   │   ├── DashboardView.vue
    │   │   ├── ProfileView.vue
    │   │   ├── MatchDetailView.vue
    │   │   └── IncomeView.vue
    │   ├── messages/
    │   │   ├── ConversationListView.vue
    │   │   └── ChatView.vue
    │   └── admin/
    │       └── AdminDashboardView.vue
    │
    ├── components/             # Reusable UI
    │   ├── common/              # Buttons, modals, toasts, loaders
    │   ├── tutor/               # Tutor card, availability editor, subject picker
    │   ├── match/               # Status badge, invitation form, timeline
    │   ├── session/             # Session form, edit-history viewer
    │   ├── review/              # Rating sliders, three-way review forms
    │   └── stats/               # Income/expense charts (Chart.js)
    │
    └── composables/
        └── useMatchDetail.js    # Shared logic between parent/tutor MatchDetail views
```

The `@/` alias (configured in `vite.config.js`) resolves to `src/`, so imports like `import { useAuthStore } from '@/stores/auth'` work from anywhere.

---

## Routes and Role Guards

Route definitions live in `src/router/index.js`. A global `beforeEach` guard:

1. Redirects unauthenticated users hitting protected routes to `/login`.
2. Enforces role restrictions on role-scoped routes (e.g. `/parent/*` requires `role === 'parent'`).
3. Redirects logged-in users away from `/login` and `/register` to their role's dashboard.

Role detection reads from the Pinia `auth` store, which rehydrates JWT state from `localStorage` on app boot.

---

## State Management

Pinia is the single source of truth for cross-view state. Stores are deliberately thin — they cache API responses and expose actions that call into `src/api/*`. Component-local state stays in `ref()` / `reactive()`.

| Store | Responsibility |
|-------|----------------|
| `auth` | Access & refresh tokens, current user, login / logout / refresh flow, role |
| `tutor` | Search filters, paginated results, cached tutor profiles |
| `match` | Match list, selected match detail, status transition actions |
| `message` | Conversation list, unread counts (polled), active thread messages |
| `toast` | Global toast queue; call `toast.success(...)` / `toast.error(...)` from anywhere |

---

## API Layer

`src/api/index.js` configures a single axios instance:

- `baseURL` from `baseURL.js` (see Environment Variables).
- **Request interceptor** — attaches `Authorization: Bearer <access_token>` from the auth store.
- **Response interceptor** — on 401, attempts a refresh-token call and retries the original request once; on 2xx, unwraps the `{ success, data, message }` envelope.
- Per-resource modules (`auth.js`, `tutors.js`, ...) export named functions mirroring backend endpoints — keeps call sites small and greppable.

Example:

```js
import { searchTutors } from '@/api/tutors'

const { data } = await searchTutors({ subject: 'math', minRating: 4 })
```

---

## Build Output and Nginx

`npm run build` produces `dist/` with:

- `index.html`
- `assets/` — hashed JS/CSS bundles. `manualChunks` splits `vendor` (vue, router, pinia, axios) and `charts` (chart.js, vue-chartjs) into separate files for better caching.
- Source maps are **disabled** in production (`vite.config.js`: `build.sourcemap: false`).

The production `Dockerfile` is a two-stage build: a Node image runs `npm run build`, then the `dist/` folder is copied into an `nginx-unprivileged` image that listens on **8080** (non-root nginx cannot bind <1024). `docker-compose.yml` maps host `80 → 8080` so the site is still served at `http://localhost/`. Nginx serves the SPA and proxies `/api/*` and `/health` to the `api` container.

Relevant bits of `nginx.conf`:

- `limit_req_zone $binary_remote_addr zone=api_edge:10m rate=20r/s;` — edge-layer rate limit applied to `/api/*` with `burst=40 nodelay`; this is the first gate before FastAPI's `RateLimitMiddleware`.
- `location /api/ { proxy_pass http://api:8000; }` — note: **no trailing slash** on the proxy target, so the `/api/` prefix is preserved when reaching the backend. Changing this to `http://api:8000/` would strip the prefix and every endpoint would 404.
- `location / { try_files $uri $uri/ /index.html; }` — SPA fallback for client-side routing.
- `location = /index.html` — explicit `no-store` so clients always fetch a fresh entry document (prevents loading a stale index that references hashed assets that no longer exist).
- `location /assets/ { expires 1y; }` — long cache for hashed bundles.
- Global security headers (CSP, HSTS, X-Frame-Options, ...) are re-declared in every `location` that sets any header, because nginx's `add_header` does not inherit across `location` blocks once the block sets even a single header.

---

## Troubleshooting

**`Network Error` on every API call in dev**
The backend isn't running. Start it with `start.bat` in `../tutor-platform-api/`, or `docker compose up`.

**CORS error in the browser console**
The API's `CORS_ORIGINS` doesn't include the frontend origin. For local dev, set `CORS_ORIGINS=http://localhost:5273` in `../tutor-platform-api/.env` (the shipped `.env.example` already uses 5273, but `Settings`'s built-in default is 5173 — watch for this mismatch if you copy defaults straight from `config.py`).

**Pages 404 after refresh in production**
Nginx SPA fallback isn't configured. The shipped `nginx.conf` handles this with `try_files ... /index.html`. If you're serving the bundle through a different server, add an equivalent fallback.

**`/api/api/auth/login` in network tab**
`VITE_API_BASE_URL` was set to `/api`. The frontend already includes `/api/` in every path — the base URL should be empty (Docker) or a full origin (dev). See [the empty-baseURL pattern](#the-empty-baseurl-pattern).

**Swagger UI at `/docs` returns 404 in production**
Intentional. The API sets `DEBUG=false` by default, which suppresses `/docs`, `/redoc`, and `/openapi.json` so the route inventory is not exposed to anonymous scanners. Set `DEBUG=true` in `tutor-platform-api/.env.docker` to re-enable it.

**Charts don't render**
`chart.js` is split into its own chunk via `manualChunks`. Confirm the `charts-*.js` bundle is being served (check Network tab). If Nginx is returning 404 for hashed assets, the `dist/` copy step in the Dockerfile didn't pick up the latest build — rebuild the image with `docker compose build --no-cache web`.

**Toast notifications don't appear**
`main.js` must mount the toast container (usually via `<Toast />` in `App.vue`). Check that the `toast` Pinia store is being read by a rendered component.

**Role-based redirect loops**
Happens if the auth store thinks the user is logged in but the backend rejects the token. Clear `localStorage` and log in again. Root cause is usually a stale token after the backend's `JWT_SECRET_KEY` was rotated.
