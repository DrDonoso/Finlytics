# AGENTS.md — Finlytics contributor guide for AI agents

## Docker / build

**One `Dockerfile`, two targets.** There is no `Dockerfile.local` any more — it was a
workaround for an `npm 10.x` crash inside Docker ("Exit handler never called", bin-symlink
bug) that no longer reproduces on `node:26-alpine` / npm 11. Do not reintroduce a second
Dockerfile without evidence that the main one fails.

| Target | Produces | Used by |
|--------|----------|---------|
| `base` *(default)* | `node:26-alpine` compiles the SPA, `python:3.14-slim` serves API + SPA. | CI/prod — `docker-compose.yml`, `docker-compose.local.yml` |
| `demo` | The same SPA built with `VITE_DEMO=1`, served by `nginx:alpine`. No Python, no API, no database. | Public demo — `docker-compose.demo.yml` |

```
frontend-deps  (npm ci)            ← shared layer, runs once
├── frontend-builder (npm run build)       → dist/
└── demo-builder     (npm run build:demo)  → dist-demo/
```

> **The `base` stage must stay LAST.** A bare `docker build .` builds the final stage, so moving `demo` below it would silently make the demo image the production build.

> **Never fold the demo into the `base` image.** It ships the production SPA bundle and its entrypoint runs `alembic upgrade head`, so serving the demo from it would require a live database and expose the real API (`/api/imports` bills OpenAI, the connector form asks for real broker tokens, `/api/auth/setup` reopens whenever the DB is empty).

> **`frontend/.env.demo` must stay un-ignored in `.dockerignore`.** The generic `.env.*` rule would swallow it, and Vite would then silently build the *production* bundle into the demo image. The `demo-builder` stage greps the output for the MSW worker to make that failure loud.

### Local dev workflow

```bash
docker compose -f docker-compose.local.yml up -d --build
```

Identical to `docker-compose.yml` but builds from the working tree instead of pulling the
published image — use it to run uncommitted code. No host pre-build step: the Dockerfile
compiles the SPA itself.

### CI/prod workflow

Push to `main` → GitHub Actions runs `docker-deploy.yml` → builds `drdonoso/finlytics`
(default target) and `drdonoso/finlytics-demo` (`--target demo`) on the same CalVer tag.
The `IMAGE_TAG` / `BUILD_DATE` build args are injected there and surfaced by
`GET /api/version` (shown on the About page).

> **Rule:** Never add a "build frontend" step to the CI workflow. The `Dockerfile` handles it.

---

## Migrations

Alembic migrations live in `alembic/versions/`. The current head is `0017_add_transaction_is_system.py`.

- Always create a new numbered migration (`0018_...`) for schema changes.
- Verify the head before writing one — this file goes stale. `down_revision` in the
  highest-numbered file is the source of truth, not this document.
- The entrypoint runs `alembic upgrade head` automatically on container start.
- Never modify an existing migration that has been deployed.

---

## Investment connector architecture

Two connector types coexist under the same plugin model:

| Type | Example | Storage |
|------|---------|---------|
| **Live-API** | Indexa Capital | Token encrypted with Fernet → `investment_connections`. Portfolio fetched on demand and cached 24h in `investment_portfolio_cache`. |
| **Statement-Import** | Fidelity ESPP | Lots stored in `espp_lots`. Daily MSFT close stored in `price_history` (via Yahoo Chart API). No token required. |

Both produce data consumed by `GET /api/investments/combined-overview`.

### Token encryption

All connector API tokens are encrypted at rest using Fernet (AES-128-CBC + HMAC-SHA256).

- Key: `FINLYTICS_ENCRYPTION_KEY` env var (must be a valid Fernet key).
- Fail-closed: any encrypt/decrypt operation raises `EncryptionNotConfiguredError` → HTTP 503 when the key is absent or invalid.
- Tokens NEVER appear in logs, API responses, or any non-encrypted DB column.

---

## Backend conventions

- **Routers:** `APIRouter(prefix="/...", tags=["..."])` per module in `src/finlytics/api/`. Registered in `app.py` with `app.include_router(router, prefix="/api", dependencies=_auth)`.
- **Schemas:** Pydantic `BaseModel` in `schemas.py`. Amounts as `float`, percentages as raw numbers (e.g. `12.5` = 12.5%).
- **Auth:** All `/api/*` routes (except `/api/auth/*`) are auth-gated via the `get_current_user` dependency.
- **Config:** `pydantic-settings` `BaseSettings` in `config.py` — env vars + `.env` file.

## Frontend conventions

- **Routing:** `App.tsx` — nested routes under `<Route path="/" element={<Layout />}>`.
- **i18n:** Bilingual EN/ES. `Dict` interface in `i18n/index.ts`, implementations in `es.ts` / `en.ts`. All three files must be updated for every new string.
- **API client:** `frontend/src/api/client.ts` — typed `apiFetch<T>()`. New endpoints follow the `getX()` / `postX()` pattern.
  - **Mock layer:** `frontend/src/api/mock.ts`, activated build-time by `VITE_USE_MOCK=1`. Coverage is **partial** — roughly 40 of 68 client functions have a mock branch. Rules, backup, statements, all Fidelity endpoints and `combined-overview` have none.
  - ⚠️ **Gotcha:** 13 functions also fall back to the mock on *any* thrown error (`catch { return mockGetX() }`), not just when `USE_MOCK` is set. In production a 500 or a network drop therefore renders **fake data as if it were the user's**. Do not copy this pattern into new endpoints; prefer letting the error surface.
- **Tests:** there is no frontend test runner (`package.json` has only `dev` / `build` / `preview`). `npm run build` runs `tsc --noEmit` first, so type errors do fail the build — that is the only automated frontend gate.
- **Plugin view registry:** `frontend/src/investments/registry.ts` — maps `plugin_id → { icon, name, component }`. Add an entry here for any new investment connector view.
- **Design tokens:** Single `index.css` with CSS custom properties (`--bg`, `--surface`, `--border`, `--primary`, `--radius`, `--shadow`). Light/dark via `[data-theme="dark"]`.

## Public demo (`frontend/src/demo/`)

`npm run build:demo` (flag `VITE_DEMO=1`, via `.env.demo`) emits a backend-less build to
`frontend/dist-demo/`: [MSW](https://mswjs.io) intercepts `/api/*` in the browser and answers
from a synthetic dataset.

CI publishes it as `drdonoso/finlytics-demo` (`docker build --target demo`). It is deployed
from `docker-compose.demo.yml` — a single nginx container, no API, no database, no volumes.
That file's header carries the operational notes; the one that bites is:

> **The demo only works over HTTPS** (or `localhost`). Its whole API layer is a Service
> Worker, and browsers refuse to register those outside a secure context. On plain HTTP the
> worker never starts and every screen fails to load — `main.tsx` catches this and renders an
> explicit message rather than a broken app.

The same `dist-demo/` also deploys to a static CDN, which is the better home for a public
demo — it needs no inbound access to your own network and gets HTTPS for free. Three files
exist for that path and must stay in sync with `nginx.demo.conf`:

| File | Platform | Purpose |
|------|----------|---------|
| `frontend/wrangler.jsonc` | Cloudflare Workers | Pure static (no `main`); `not_found_handling: single-page-application` is the SPA fallback |
| `dist-demo/_redirects` | Pages / Netlify | `/* /index.html 200` SPA fallback |
| `dist-demo/_headers` | Pages / Workers / Netlify | `no-cache` on the worker, immutable `/assets/*`, security headers |

`_redirects` and `_headers` are emitted by a `vite.config.ts` plugin in demo mode rather
than committed under `public/`, because everything in `public/` is also copied into the
**production** bundle, where FastAPI serves the SPA and they would be dead weight.

| File | Role |
|------|------|
| `config.ts` | `IS_DEMO` flag, the `demo`/`demo` credentials, and the connector allowlist |
| `scenario.ts` | Seeded generator — accounts, transactions, Indexa portfolio and Fidelity ESPP lots. **Dates are relative to today** because `defaultRange()` opens on the previous calendar month; hardcoded dates would go stale. ESPP purchases land on the last weekday of Mar/Jun/Sep/Dec, mirroring `api/fidelity.py`. |
| `store.ts` | Single source of truth: the ledger AND every aggregate derive from one transaction list, so an edit is reflected in the KPIs. Filter semantics mirror `db/queries.py::_apply_filters`. |
| `handlers.ts` | MSW routes, plus a catch-all that answers 501 and logs `[demo] Unhandled API request:` |
| `browser.ts` | Worker startup — awaited in `main.tsx` **before** React mounts (AuthProvider fetches on its first effect) |
| `DemoLoginNotice.tsx` | The demo disclaimer, shown **only** on the login card |
| `nginx.demo.conf` | Serves the demo image. SPA fallback for deep links; `mockServiceWorker.js` must never be cached. Only the demo uses nginx — in production FastAPI serves the SPA itself. |

The demo keeps a real login screen: `/api/auth/status` starts unauthenticated and
`/api/auth/login` only accepts `demo`/`demo` (anything else 401s), so the sign-in flow
demoes itself. Session state is a module variable in `handlers.ts`, so a reload logs the
visitor back out — the same reset that restores the dataset.

> **Keep the disclaimer on the login screen only.** It is there to set expectations once,
> before the visitor is inside. A persistent banner would cover the UI on every page,
> which is the thing the demo exists to show.

> **Percentage units are not uniform across the API** — mirror the backend, don't guess.
> `combined-overview` (`total_gain_loss_pct`, `providers[].gain_loss_pct`, every `pct`),
> `fidelity/kpis.gain_loss_pct` and `fidelity/lots[].gain_loss_pct` are all **percentages**
> (25.4 = 25.4%), while `InvestmentPortfolio.total_gain_loss_pct` and its `returns.*` are
> **decimal fractions**. The UI prints most of them with a bare `.toFixed(1)`, so getting
> this wrong renders "+0.3 %" instead of "+25.4 %" and nothing throws.

Rules when touching the frontend:

- **A new `/api` endpoint reached by a demo route needs a handler in `handlers.ts`**, or the demo
  silently loses that screen. The catch-all's console error is the signal.
- Demo mode intentionally exposes a reduced surface (`DemoRoutes` in `App.tsx`). Anything that
  writes, uploads or asks for third-party credentials stays out.
- Keep the demo free of MSW leakage into production: the dynamic import in `main.tsx` is guarded
  by a literal `import.meta.env.VITE_DEMO` check so the bundler can drop it.
