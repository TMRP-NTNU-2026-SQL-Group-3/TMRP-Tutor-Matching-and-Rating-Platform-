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
├── Dockerfile                       # Multi-stage: Vite build → nginx-unprivileged static serve
├── nginx.conf                       # /api/* → api:8000, SPA fallback, asset caching,
│                                    # edge rate limit (20 r/s, burst 40), HSTS gated on x-forwarded-proto
├── nginx-security-headers.conf      # Shared CSP / X-Frame-Options / Referrer-Policy snippet
│                                    # included from every `location` that calls add_header
├── vite.config.js                   # Port 5273, @ alias, dev proxy (/api → localhost:8000),
│                                    # vendor/charts manual chunks, sourcemap off, SRI plugin
├── vite-plugin-sri.js               # Post-build plugin: injects sha384 integrity attributes
│                                    # into index.html for every emitted JS/CSS chunk
├── index.html
├── package.json
├── .env.development / .env.production / .env.example
├── scripts/
│   ├── check-no-v-html.mjs          # Pre-build lint: fail if any template uses v-html
│   └── pin-base-images.sh           # Pin Docker base images to current digests for reproducible builds
└── src/
    ├── main.js                      # App bootstrap: Pinia, router, global styles
    ├── App.vue
    ├── constants.js                 # Shared enums (roles, match status values, labels, ...)
    ├── style.css                    # Tailwind entry
    │
    ├── router/
    │   └── index.js                 # Route table, role-based navigation guards
    │
    ├── stores/                      # Pinia stores
    │   ├── auth.js                  # Current user, role, verified flag, login/logout/refresh flow
    │   │                            # (tokens themselves live in HttpOnly cookies — never in JS)
    │   ├── tutor.js                 # Tutor search filters, results, profile cache
    │   ├── notifications.js         # In-app notification history (per-user localStorage, 1 h TTL)
    │   └── toast.js                 # Global toast notifications
    │
    ├── api/                         # Axios service layer (one file per resource)
    │   ├── index.js                 # Axios instance: baseURL, auth interceptor, error mapping
    │   ├── baseURL.js               # API_BASE_URL resolver (see Environment Variables)
    │   ├── authHandler.js           # Shared 401 / refresh-token handler reused by the interceptor
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
    ├── views/                       # Page-level components (mapped by router)
    │   ├── LoginView.vue
    │   ├── RegisterView.vue
    │   ├── NotFoundView.vue         # 404 fallback for unmatched routes
    │   ├── parent/
    │   │   ├── DashboardView.vue
    │   │   ├── SearchView.vue
    │   │   ├── TutorDetailView.vue
    │   │   ├── MatchDetailView.vue
    │   │   ├── StudentsView.vue
    │   │   ├── ProfileView.vue
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
    ├── components/                  # Reusable UI
    │   ├── common/                  # AppNav, PageHeader, StatCard, StatusBadge, EmptyState,
    │   │                            # ConfirmDialog, ToastNotification, NotificationBell
    │   ├── tutor/                   # TutorCard, TutorFilter, AvailabilityCalendar
    │   ├── match/                   # InviteForm, ContractForm, ContractConfirmModal
    │   ├── session/                 # SessionForm, SessionTimeline (edit-history viewer)
    │   ├── review/                  # RadarChart (per-dimension rating), ReviewList
    │   └── stats/                   # IncomeChart, ExpenseChart, ProgressChart (Chart.js)
    │
    ├── composables/
    │   ├── useMatchDetail.js        # Shared logic between parent/tutor MatchDetail views
    │   └── useConfirm.js            # Promise-based wrapper around the global ConfirmDialog
    │
    └── utils/
        ├── format.js                # Locale-safe date/time formatters (avoid TZ off-by-one)
        └── highlight.js             # Search-term highlight splitter — returns segment array,
                                     # never raw HTML (XSS-safe, paired with the no-v-html lint)
```

The `@/` alias (configured in `vite.config.js`) resolves to `src/`, so imports like `import { useAuthStore } from '@/stores/auth'` work from anywhere.

---

## Routes and Role Guards

Route definitions live in `src/router/index.js`. A global `beforeEach` guard:

1. Redirects unauthenticated users hitting protected routes to `/login`.
2. Enforces role restrictions on role-scoped routes (e.g. `/parent/*` requires `role === 'parent'`). The `/messages/*` subtree uses both an `roles: ['parent', 'tutor']` allow-list **and** an `excludeRoles: ['admin']` deny-list as belt-and-braces — admin has no chat surface.
3. Redirects logged-in users away from `/login` and `/register` to their role's dashboard.
4. Awaits `auth.ensureVerified()` on every protected navigation (not just the first one). `ensureVerified()` short-circuits on a cached verification, so the cost is one function call but it closes the window where a tampered `localStorage.user` could bypass the role check on in-session navigations.

Role detection reads from the Pinia `auth` store. On app boot the store rehydrates cached user info (role, display name) from `localStorage`; auth tokens themselves live in HttpOnly cookies and are never accessible to JavaScript. `ensureVerified()` hits `GET /api/auth/me` to obtain an authoritative role from the server before trusting the cached value.

---

## State Management

Pinia is the single source of truth for cross-view state. Stores are deliberately thin — they cache API responses and expose actions that call into `src/api/*`. Component-local state stays in `ref()` / `reactive()`.

| Store | Responsibility |
|-------|----------------|
| `auth` | Current user, role, `verified` flag, login / logout / refresh-on-401 flow. Tokens live in HttpOnly cookies and are never accessible to JavaScript; only non-sensitive user info is cached in `localStorage`. |
| `tutor` | Search filters, paginated results, cached tutor profiles |
| `notifications` | In-app notification history, scoped per-user in `localStorage` with a 1-hour TTL so a shared device cannot leak the previous session's notifications |
| `toast` | Global toast queue; call `toast.success(...)` / `toast.error(...)` from anywhere |

Match list, conversation list, and chat history are kept as component-local state in their respective views — they did not justify a dedicated store.

---

## API Layer

`src/api/index.js` configures a single axios instance:

- `baseURL` from `baseURL.js` (see Environment Variables).
- `withCredentials: true` — auth tokens travel as HttpOnly cookies, sent automatically by the browser on every request. JS never holds the access or refresh token.
- **Request interceptor** — attaches a shared `AbortController` signal (so `logout()` can cancel every in-flight request) and, on mutating methods (POST/PUT/PATCH/DELETE), reflects the readable `csrf_token` cookie into an `X-CSRF-Token` header plus `X-Requested-With: XMLHttpRequest`. This implements the double-submit-cookie CSRF defence enforced by the backend's `CSRFMiddleware`.
- **Response interceptor** — unwraps the `{ success, data, message }` envelope on JSON responses (passes blobs and HTML upstream errors through untouched); on 401, runs a single in-flight `POST /api/auth/refresh` and retries the original request once; on 5xx / network errors, retries up to twice with exponential backoff. 5xx error messages are sanitised to a generic string before reaching the user, while the raw message is logged in dev mode.
- Per-resource modules (`auth.js`, `tutors.js`, ...) export named functions mirroring backend endpoints — keeps call sites small and greppable.

Example:

```js
import { searchTutors } from '@/api/tutors'

const { data } = await searchTutors({ subject: 'math', minRating: 4 })
```

---

## Build Output and Nginx

`npm run build` produces `dist/` with:

- `index.html` — every emitted `<script>` and `<link rel="stylesheet">` carries an `integrity="sha384-..."` attribute injected by `vite-plugin-sri.js`, so the browser refuses to execute a tampered bundle.
- `assets/` — hashed JS/CSS bundles. `manualChunks` splits `vendor` (vue, router, pinia, axios) and `charts` (chart.js, vue-chartjs) into separate files for better caching.
- Source maps are **disabled** in production (`vite.config.js`: `build.sourcemap: false`).

The SRI plugin runs in the `writeBundle` hook (post-enforce), not `generateBundle`, because Vite's `vite:build-import-analysis` plugin rewrites entry-chunk code to inline `__VITE_PRELOAD__` lists after `generateBundle` returns — hashing the in-memory chunk there yields a stale digest and the browser silently blocks the script. Reading the on-disk bytes after the bundle is fully written guarantees the hash matches what the browser fetches.

The production `Dockerfile` is a two-stage build: a Node image runs `npm run build`, then the `dist/` folder is copied into an `nginx-unprivileged` image that listens on **8080** (non-root nginx cannot bind <1024). `docker-compose.yml` maps host `80 → 8080` so the site is still served at `http://localhost/`. Nginx serves the SPA and proxies `/api/*` and `/health` to the `api` container.

Relevant bits of `nginx.conf`:

- `limit_req_zone $binary_remote_addr zone=api_edge:10m rate=20r/s;` — edge-layer rate limit applied to `/api/*` with `burst=40 nodelay`; this is the first gate before FastAPI's `RateLimitMiddleware`.
- `location /api/ { proxy_pass http://api:8000; }` — note: **no trailing slash** on the proxy target, so the `/api/` prefix is preserved when reaching the backend. Changing this to `http://api:8000/` would strip the prefix and every endpoint would 404.
- `location / { try_files $uri $uri/ /index.html; }` — SPA fallback for client-side routing.
- `location = /index.html` — explicit `no-store` so clients always fetch a fresh entry document (prevents loading a stale index that references hashed assets that no longer exist).
- `location /assets/ { expires 1y; }` — long cache for hashed bundles.
- `proxy_cookie_flags ~.* secure samesite=lax` on `/api/` — asserts `Secure` and `SameSite=Lax` on every proxied `Set-Cookie`, so a missing flag from the backend cannot reach the browser unpatched.
- `proxy_set_header X-Forwarded-For $remote_addr` — overwrites rather than appends, pinning the IP seen by the backend's rate limiter and audit log to the real peer address. Appending the client-supplied value would let an attacker spoof the origin IP.
- Security headers (CSP, X-Frame-Options, Referrer-Policy, ...) live in `nginx-security-headers.conf` and are `include`d from every `location` that calls `add_header`, because nginx's `add_header` does **not** inherit across `location` blocks once the block sets any header. HSTS is emitted via a `map $http_x_forwarded_proto $hsts_header` so the header is only set when the upstream TLS terminator confirms HTTPS.

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
Happens if the auth store thinks the user is logged in but the backend rejects the session. Clear `localStorage` *and* delete the `access_token` / `refresh_token` cookies via the browser's DevTools (Application → Cookies), then reload and log in again. Root cause is usually a stale cookie after the backend's `JWT_SECRET_KEY` was rotated. Note: tokens are in HttpOnly cookies — clearing `localStorage` alone is not sufficient.
