# ─── Stage 1: Shared npm dependency layer ────────────────────────────────────
# Split out so the production SPA and the demo SPA reuse the SAME `npm ci`
# layer. It only re-runs when the lock file changes.
FROM node:26-alpine AS frontend-deps

WORKDIR /frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci


# ─── Stage 2a: Production SPA ────────────────────────────────────────────────
FROM frontend-deps AS frontend-builder

COPY frontend/ ./
RUN npm run build
# → output: /frontend/dist/


# ─── Stage 2b: Demo SPA ──────────────────────────────────────────────────────
# `--mode demo` loads frontend/.env.demo (VITE_DEMO=1), swapping the app onto
# the in-browser synthetic dataset served by MSW. No API, no database.
FROM frontend-deps AS demo-builder

COPY frontend/ ./
RUN npm run build:demo
# → output: /frontend/dist-demo/

# Guard: if frontend/.env.demo is missing from the build context (a .dockerignore
# rule is one `.env.*` away from swallowing it), Vite still builds happily — but
# VITE_DEMO is unset, so it emits the PRODUCTION bundle with no mock API. The
# resulting "demo" image would 404 on every request. Fail here instead.
RUN grep -rq "mockServiceWorker" dist-demo/assets/ || { \
      echo "ERROR: demo bundle has no MSW worker registration."; \
      echo "       Is frontend/.env.demo present in the Docker build context?"; \
      exit 1; \
    }


# ─── Stage 3: Demo runtime — `docker build --target demo` ────────────────────
# Static nginx image for the public demo: no Python, no API, no database.
# Kept OUT of the default target on purpose; see the note on the last stage.
FROM nginx:alpine AS demo

COPY nginx.demo.conf /etc/nginx/conf.d/default.conf
COPY --from=demo-builder /frontend/dist-demo /usr/share/nginx/html

ARG IMAGE_TAG=""
ARG BUILD_DATE=""
LABEL org.opencontainers.image.title="Finlytics Demo" \
      org.opencontainers.image.description="Static Finlytics demo with synthetic data — no backend, no database" \
      org.opencontainers.image.version="$IMAGE_TAG" \
      org.opencontainers.image.created="$BUILD_DATE" \
      org.opencontainers.image.source="https://github.com/DrDonoso/Finlytics"

EXPOSE 7778

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -qO- http://127.0.0.1:7778/healthz || exit 1


# ─── uv binary ───────────────────────────────────────────────────────────────
# A FROM line of its own, so Dependabot's docker ecosystem bumps it, and CI reads
# the same tag. The base stage mounts the binary instead of copying it.
FROM ghcr.io/astral-sh/uv:0.12.19 AS uv


# ─── Stage 4: Python runtime (DEFAULT TARGET — keep last) ────────────────────
# A plain `docker build .` builds the LAST stage, so this one must stay at the
# bottom: moving it above `demo` would silently make the demo image the default
# production build.
FROM python:3.14-slim AS base

# The base image runs in UTC. The application resolves its calendar day from
# TIMEZONE (see finlytics/clock.py), but the process clock is worth aligning too
# so log timestamps match what the UI shows. docker-compose injects TZ alongside
# TIMEZONE.
ENV TZ=Europe/Madrid

# Create non-root user
RUN groupadd --gid 1000 app && \
    useradd --uid 1000 --gid app --create-home app

WORKDIR /app

# Dependencies come from uv.lock, and --locked fails the build when the lock is
# out of date with pyproject.toml instead of silently re-resolving. uv is only
# mounted for the install steps, so the binary never reaches the image. The venv
# is first on PATH, so the entrypoint's `alembic` and `python` resolve to it.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_CACHE=1 \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/app/.venv/bin:$PATH"

# Dependencies only, so this layer re-runs when the lock changes, not on code edits.
COPY pyproject.toml uv.lock ./
RUN --mount=from=uv,source=/uv,target=/usr/local/bin/uv \
    uv sync --locked --no-dev --no-install-project

# Create writable dir for uploads BEFORE copying source,
# so this layer stays cached when only the app code changes.
RUN mkdir -p /app/data/uploads && chown -R app:app /app/data

# The project itself, as a regular (non-editable) install. README.md and LICENSE
# are referenced by the [project] readme / license-files metadata.
# These are the only layers that change on a normal code update.
COPY README.md LICENSE ./
COPY src/ ./src/
RUN --mount=from=uv,source=/uv,target=/usr/local/bin/uv \
    uv sync --locked --no-dev --no-editable

# Copy migration + seed artefacts (needed by the entrypoint)
COPY alembic.ini seed.py ./
COPY alembic/ ./alembic/
COPY scripts/ ./scripts/

# Copy the compiled React SPA from the frontend stage
COPY --from=frontend-builder /frontend/dist ./frontend/dist

# Entrypoint: runs migrations + seed → exec uvicorn
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN sed -i 's/\r$//' /docker-entrypoint.sh && chmod +x /docker-entrypoint.sh

ARG IMAGE_TAG=""
ARG BUILD_DATE=""
ENV FINLYTICS_IMAGE_TAG=$IMAGE_TAG
ENV FINLYTICS_BUILD_DATE=$BUILD_DATE

EXPOSE 7777

USER app

ENTRYPOINT ["/docker-entrypoint.sh"]
