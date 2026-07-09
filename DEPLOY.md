# Finlytics — Deployment Guide

## Quick start (local)

```bash
cp .env.example .env          # fill in POSTGRES_PASSWORD (required)
docker compose -f docker-compose.yml -f docker-compose.local.yml up --build
```

The stack starts on `http://localhost:7777` (override with `FINLYTICS_PORT` in `.env`).  
On first boot the entrypoint automatically runs `alembic upgrade head` and seeds the base categories.

---

## Image

| Registry | Image |
|----------|-------|
| Docker Hub | `drdonoso/finlytics` |

The image is a **multi-stage build**:
1. `node:20-alpine` — builds the React/Vite frontend (`npm ci && npm run build`)
2. `python:3.12-slim` — installs the Python package, copies the compiled SPA, and ships the final image

---

## GitHub Actions — required secrets

The workflow (`.github/workflows/docker-deploy.yml`) needs **two repository secrets** set in the GitHub UI:

| Secret name | Where to find it |
|-------------|-----------------|
| `DOCKER_USERNAME` | Your Docker Hub username (e.g. `drdonoso`) |
| `DOCKER_PASSWORD` | A Docker Hub **Access Token** (not your password) — create at https://hub.docker.com/settings/security |

**How to set them:**  
Repository → Settings → Secrets and variables → Actions → New repository secret

---

## Manual steps to connect repo → GitHub → Docker Hub

1. **Create the GitHub repository** (empty, no README) at https://github.com/new
2. **Add the remote and push:**
   ```bash
   git remote add origin https://github.com/<your-user>/Finlytics.git
   git push -u origin main
   ```
3. **Set the two secrets** listed above.
4. Every push to `main` now triggers: lint → test → Docker multi-stage build → push to Docker Hub (tagged `latest` + CalVer).

---

## Production deployment (server)

Copy `.env.example` → `.env` on the server, fill in values, then:

```bash
docker compose pull
docker compose up -d
```

This uses only `docker-compose.yml` (published image, no local build needed).

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
| `FINLYTICS_PORT` | — | `7777` | Host port |
| `TIMEZONE` | — | `Europe/Madrid` | Display timezone |
| `AUTH_SECRET` | — | random per boot | Secret for signing session JWTs. **Set a fixed value in production** (otherwise every restart invalidates all sessions). Generate: `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `AUTH_COOKIE_SECURE` | — | `false` | Set to `true` when serving over **HTTPS** so the session cookie gets the `Secure` flag. Keep `false` only for local `http://localhost`. |

> **Production security:** behind HTTPS, always set `AUTH_COOKIE_SECURE=true` and a fixed `AUTH_SECRET`. The cookie is already `HttpOnly` + `SameSite=Lax`.
