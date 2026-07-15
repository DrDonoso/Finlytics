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
