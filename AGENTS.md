# AGENTS.md — Finlytics contributor guide for AI agents

## Docker / build

Two Dockerfiles exist in this repo:

| File | Purpose | Used by |
|------|---------|---------|
| `Dockerfile` | **Multi-stage, multi-target.** Default target `base`: `node:26-alpine` compiles the SPA, `python:3.14-slim` serves API + SPA. Target `demo` (`docker build --target demo`): the same SPA built with `VITE_DEMO=1`, served by `nginx:alpine` — no Python, no API, no database. Both frontend builds share one `npm ci` layer. | CI/prod (`docker-compose.yml`), public demo (`docker-compose.demo.yml`) |
| `Dockerfile.local` | **Host-prebuilt frontend** — skips the Node stage; expects `frontend/dist/` to already exist on the host. | Local dev (`docker-compose.local.yml`) |

> **The `base` stage must stay LAST.** A bare `docker build .` builds the final stage, so moving `demo` below it would silently make the demo image the production build.

> **Never fold the demo into the `base` image.** It ships the production SPA bundle and its entrypoint runs `alembic upgrade head`, so serving the demo from it would require a live database and expose the real API (`/api/imports` bills OpenAI, the connector form asks for real broker tokens, `/api/auth/setup` reopens whenever the DB is empty).

> **`frontend/.env.demo` must stay un-ignored in `.dockerignore`.** The generic `.env.*` rule would swallow it, and Vite would then silently build the *production* bundle into the demo image. The `demo-builder` stage greps the output for the MSW worker to make that failure loud.

### Why two files?

`npm 10.x` crashes inside Docker on the owner's machine ("Exit handler never called" — bin-symlink bug). The main `Dockerfile` works fine in CI (GitHub Actions / Linux runners) and is the source of truth for production images.

### Local dev workflow

```bash
cd frontend && npm run build          # build SPA on host
docker compose -f docker-compose.local.yml build
docker compose -f docker-compose.local.yml up -d
```

### CI/prod workflow

Push to `main` → GitHub Actions runs `docker-deploy.yml` → builds with the main `Dockerfile` (full multi-stage, no host pre-build needed).

> **Rule:** Never add a "build frontend" step to the CI workflow. The main `Dockerfile` handles it.

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
from a synthetic dataset. Deployment steps are in `DEPLOY.md`.

| File | Role |
|------|------|
| `config.ts` | `IS_DEMO` flag + the connector allowlist |
| `scenario.ts` | Seeded generator — accounts, transactions, portfolio. **Dates are relative to today** because `defaultRange()` opens on the previous calendar month; hardcoded dates would go stale. |
| `store.ts` | Single source of truth: the ledger AND every aggregate derive from one transaction list, so an edit is reflected in the KPIs. Filter semantics mirror `db/queries.py::_apply_filters`. |
| `handlers.ts` | MSW routes, plus a catch-all that answers 501 and logs `[demo] Unhandled API request:` |
| `browser.ts` | Worker startup — awaited in `main.tsx` **before** React mounts (AuthProvider fetches on its first effect) |

Rules when touching the frontend:

- **A new `/api` endpoint reached by a demo route needs a handler in `handlers.ts`**, or the demo
  silently loses that screen. The catch-all's console error is the signal.
- Demo mode intentionally exposes a reduced surface (`DemoRoutes` in `App.tsx`). Anything that
  writes, uploads or asks for third-party credentials stays out.
- Keep the demo free of MSW leakage into production: the dynamic import in `main.tsx` is guarded
  by a literal `import.meta.env.VITE_DEMO` check so the bundler can drop it.
