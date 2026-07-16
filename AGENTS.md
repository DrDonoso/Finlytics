# AGENTS.md — Finlytics contributor guide for AI agents

## Docker / build

Two Dockerfiles exist in this repo:

| File | Purpose | Used by |
|------|---------|---------|
| `Dockerfile` | **Full multi-stage build** — Node 20 compiles the React frontend inside Docker, then Python 3.12-slim serves API + SPA. Self-contained. | CI/prod (`docker-compose.yml`, GitHub Actions) |
| `Dockerfile.local` | **Host-prebuilt frontend** — skips the Node stage; expects `frontend/dist/` to already exist on the host. | Local dev (`docker-compose.local.yml`) |

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

Alembic migrations live in `alembic/versions/`. The current head is `0015_add_portfolio_cache.py`.

- Always create a new numbered migration (`0016_...`) for schema changes.
- The entrypoint runs `alembic upgrade head` automatically on container start.
- Never modify an existing migration that has been deployed.

---

## Investment connector architecture

Two connector types coexist under the same plugin model:

| Type | Example | Storage |
|------|---------|---------|
| **Live-API** | Indexa Capital | Token encrypted with Fernet → `investment_connections`. Portfolio fetched on demand and cached 24h in `investment_portfolio_cache`. |
| **Statement-Import** | Fidelity ESPP | Lots stored in `espp_lots`. Daily MSFT price stored in `market_data` (via Yahoo Chart API). No token required. |

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
- **API client:** `frontend/src/api/client.ts` — typed `apiFetch<T>()`. New endpoints follow the `getX()` / `postX()` pattern with mock fallback for `VITE_USE_MOCK=1`.
- **Plugin view registry:** `frontend/src/investments/registry.ts` — maps `plugin_id → { icon, name, component }`. Add an entry here for any new investment connector view.
- **Design tokens:** Single `index.css` with CSS custom properties (`--bg`, `--surface`, `--border`, `--primary`, `--radius`, `--shadow`). Light/dark via `[data-theme="dark"]`.
