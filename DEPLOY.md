# Finlytics — Deployment Guide

## Two Dockerfiles — which one to use?

| File | Target | Purpose | Used by |
|------|--------|---------|---------|
| `Dockerfile` | *(default)* `base` | **Full multi-stage build** — `node:26-alpine` compiles the React frontend inside Docker, then `python:3.14-slim` serves API + SPA. Self-contained; no host tools needed. | CI/prod (`docker-compose.yml`, GitHub Actions) |
| `Dockerfile` | `demo` | **Static public demo** — the same SPA built with `VITE_DEMO=1`, served by `nginx:alpine`. No Python, no API, no database. | Public demo (`docker-compose.demo.yml`) |
| `Dockerfile.local` | — | **Host-prebuilt frontend** — skips the Node stage; expects `frontend/dist/` to already exist on the host. | Local dev (`docker-compose.local.yml`) |

Both frontend builds share a single `npm ci` layer (`frontend-deps`), so building the
demo after the production image costs only the Vite run. The `base` stage is deliberately
last: `docker build .` builds the final stage, so a bare build always produces the
production image.

---

## Production — pull published image

Copy `.env.example` → `.env` on the server, fill in values, then:

```bash
docker compose pull
docker compose up -d
```

This uses only `docker-compose.yml` (published image from Docker Hub — `drdonoso/finlytics`). No local build needed.

On first boot the entrypoint automatically runs `alembic upgrade head` and seeds the base categories.

The stack starts on `http://localhost:7777` (override with `FINLYTICS_PORT` in `.env`).

---

## Build from source (full multi-stage — CI equivalent)

```bash
cp .env.example .env          # fill in POSTGRES_PASSWORD (required)
docker compose up -d --build
```

Uses the main `Dockerfile` — identical to what GitHub Actions runs.

---

## Local dev (host-prebuilt frontend)

Use this when `npm` inside Docker fails on your machine:

```bash
cd frontend && npm run build          # compile SPA on host → frontend/dist/
cd ..
docker compose -f docker-compose.local.yml up -d --build
```

`Dockerfile.local` copies the host-built `frontend/dist/` into the Python image without running Node inside Docker.

> **Why the local file exists:** `npm 10.x` crashes inside Docker on the owner's machine ("Exit handler never called" — bin-symlink bug). The main `Dockerfile` works fine in CI.

---

## Public demo (static, no backend)

The demo is a **separate image**, `drdonoso/finlytics-demo`: the SPA built with
`VITE_DEMO=1` and served by nginx. [MSW](https://mswjs.io) intercepts `/api/*` inside
the browser and answers from a synthetic dataset, so there is no API container, no
PostgreSQL, no secrets and no volumes.

> **It cannot be the same image as `drdonoso/finlytics`.** That one ships the production
> SPA bundle (no mock layer) and its entrypoint runs `alembic upgrade head`, so it needs a
> live database — and running it publicly would expose the real API, including the
> OpenAI-billed `/api/imports`, the Indexa token form, and `/api/auth/setup`, which
> reopens whenever the database is empty.

### Deploying (Dockge, Portainer, plain compose)

Create a stack from `docker-compose.demo.yml`:

```bash
docker compose -f docker-compose.demo.yml pull
docker compose -f docker-compose.demo.yml up -d
```

In Dockge: new stack → paste the contents of `docker-compose.demo.yml` → deploy. The
image is pulled from Docker Hub; nothing is built on the host.

| Setting | Value |
|---------|-------|
| Image | `drdonoso/finlytics-demo:latest` (also tagged with the CalVer release) |
| Container port | `80` |
| Host port | `FINLYTICS_DEMO_PORT`, default `7778` |
| Health check | `GET /healthz` → `200 ok` |
| State | None — no volumes, no env vars, no database |

### ⚠️ HTTPS is mandatory

The demo's entire API layer is a **Service Worker**, and browsers only register those in
a *secure context*: HTTPS, or `localhost`. Served from a plain `http://192.168.x.x:7778`
the worker never starts and every screen fails to load. Put the container behind your
reverse proxy with a certificate (Nginx Proxy Manager, Caddy, Traefik, a Cloudflare
tunnel — any of them will do).

If the worker cannot start, the page renders an explicit bilingual message instead of a
broken app, so this failure is easy to recognise.

### Building it yourself

```bash
docker build --target demo -t finlytics-demo:local .
docker run --rm -p 8099:80 finlytics-demo:local
```

`--target demo` is a stage of the main `Dockerfile`, so it reuses the same `npm ci`
layer as the production build.

Or without Docker, for a plain static host:

```bash
cd frontend
npm install            # once — the demo needs the msw devDependency
npm run build:demo     # → frontend/dist-demo/
npm run preview:demo   # local check
```

Serving `dist-demo/` by hand has two requirements that `nginx.demo.conf` already covers:

* **SPA fallback** — `BrowserRouter` means `/analytics` only exists client-side;
  without `try_files $uri $uri/ /index.html;` a deep link or a refresh 404s.
* **Never cache `mockServiceWorker.js`** — it is the demo's whole API layer; a stale
  copy breaks every screen.
* **Serve at the origin root** — assets are absolute (`/logo.png`, `/logos/*.svg`,
  `/mockServiceWorker.js`), so a sub-path like `/demo/` breaks them.

### What the demo does and does not include

| | |
|---|---|
| **Available** | Dashboard, Finances overview, Transactions (filters, sorting, paging), Analytics, Investments + the Indexa view. Editing a transaction works and updates every KPI, but lives in memory only. |
| **Hidden** | Statement import, statements, rules, backup, accounts/tags/categories management, connectors, Telegram, Fidelity ESPP — anything that writes, uploads, or asks for third-party credentials. |
| **Data** | Fully invented and regenerated on each page load from a fixed seed, with dates relative to today. No real person, IBAN, institution or merchant. Nothing is persisted: a reload restores the initial scenario. |

Because the demo goes through the same `api/client.ts` as production, **a new endpoint
needs a matching handler in `src/demo/handlers.ts`**. Without one, the catch-all replies
`501` and logs `[demo] Unhandled API request: …` to the console — check for that message
after adding endpoints.

Source layout: `frontend/src/demo/` — `scenario.ts` (data generation), `store.ts`
(queries and aggregates), `handlers.ts` (MSW routes), `browser.ts` (worker startup),
`config.ts` (the `VITE_DEMO` flag). The flag is build-time, so a normal
`npm run build` contains none of it.

---

## Image

| Registry | Image |
|----------|-------|
| Docker Hub | `drdonoso/finlytics` |

The main `Dockerfile` is a **multi-stage build**:
1. `node:26-alpine` — `npm ci && npm run build` → produces the React SPA in `/frontend/dist`
2. `python:3.14-slim` — installs the Python package, copies the compiled SPA, runs the entrypoint

Build-time ARGs `IMAGE_TAG` and `BUILD_DATE` are injected by CI and exposed via `GET /api/version` (used by the About page in the UI).

---

## GitHub Actions — required secrets

The workflow (`.github/workflows/docker-deploy.yml`) needs **two repository secrets** set in the GitHub UI:

| Secret name | Where to find it |
|-------------|-----------------|
| `DOCKER_USERNAME` | Your Docker Hub username (e.g. `drdonoso`) |
| `DOCKER_PASSWORD` | A Docker Hub **Access Token** (not your password) — create at https://hub.docker.com/settings/security |

**How to set them:**
Repository → Settings → Secrets and variables → Actions → New repository secret

Every push to `main` triggers: lint → test → Docker multi-stage build → push to Docker Hub (tagged `latest` + CalVer).

> **Rule:** Never add a "build frontend" step to the CI workflow. The main `Dockerfile` handles it.

---

## Environment variables reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `POSTGRES_PASSWORD` | ✅ | — | Database password |
| `POSTGRES_USER` | — | `finlytics` | Database user |
| `POSTGRES_DB` | — | `finlytics` | Database name |
| `OPENAI_API_KEY` | — | — | OpenAI API key (enables AI extraction) |
| `OPENAI_BASE_URL` | — | — | OpenAI base URL, e.g. `https://api.openai.com/v1` |
| `OPENAI_MODEL` | — | — | Model name |
| `FINLYTICS_ENCRYPTION_KEY` | — | — | Fernet key for encrypting connector API tokens at rest. Required for Indexa Capital. Generate: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `FINLYTICS_PORT` | — | `7777` | Host port |
| `TIMEZONE` | — | `Europe/Madrid` | Display timezone |
| `AUTH_SECRET` | — | random per boot | Secret for signing session JWTs. **Set a fixed value in production** (otherwise every restart invalidates all sessions). Generate: `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `AUTH_COOKIE_SECURE` | — | `false` | Set to `true` when serving over **HTTPS** so the session cookie gets the `Secure` flag. Keep `false` only for local `http://localhost`. |

> **Production security:** behind HTTPS, always set `AUTH_COOKIE_SECURE=true` and a fixed `AUTH_SECRET`. The cookie is already `HttpOnly` + `SameSite=Lax`.
