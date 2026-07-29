# Finlytics — Deployment Guide

## Two Dockerfiles — which one to use?

| File | Purpose | Used by |
|------|---------|---------|
| `Dockerfile` | **Full multi-stage build** — Node 20 compiles the React frontend inside Docker, then Python 3.12-slim serves API + SPA. Self-contained; no host tools needed. | CI/prod (`docker-compose.yml`, GitHub Actions) |
| `Dockerfile.local` | **Host-prebuilt frontend** — skips the Node stage; expects `frontend/dist/` to already exist on the host. | Local dev (`docker-compose.local.yml`) |

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

`npm run build:demo` produces a **frontend-only** build in `frontend/dist-demo/`. It
serves a synthetic dataset from the browser via [MSW](https://mswjs.io), so the demo
needs no API, no PostgreSQL and no secrets.

```bash
cd frontend
npm install            # once — the demo needs the msw devDependency
npm run build:demo     # → frontend/dist-demo/
npm run preview:demo   # optional local check on http://localhost:4173
```

Then publish `frontend/dist-demo/` on any static host (nginx, Caddy, GitHub Pages,
Netlify…). Two hosting requirements:

* **SPA fallback** — the app uses `BrowserRouter`, so every unknown path must serve
  `index.html` or a deep link like `/analytics` returns 404. In nginx:
  `try_files $uri $uri/ /index.html;`
* **Serve at the origin root** — assets are referenced absolutely (`/logo.png`,
  `/logos/*.svg`, `/mockServiceWorker.js`). Hosting under a sub-path such as
  `/demo/` breaks them.

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
