# ─── Stage 1: Build the React frontend ──────────────────────────────────────
# NOTE: npm 10.x crashes in Docker containers ("Exit handler never called"),
# skipping bin-symlink creation. Build the frontend on the host before running
# docker compose build:
#   cd frontend && npm ci && npm run build
# Then the pre-built frontend/dist/ is copied into the image below.
#
# To re-enable in-Docker builds once npm resolves the issue, restore:
#   FROM node:20-slim AS frontend-builder
#   WORKDIR /frontend
#   COPY frontend/package.json frontend/package-lock.json ./
#   RUN npm ci
#   COPY frontend/ ./
#   RUN npm run build
#   # and change the COPY below back to:
#   # COPY --from=frontend-builder /frontend/dist ./frontend/dist


# ─── Stage 2: Python runtime ──────────────────────────────────────────────────
FROM python:3.12-slim AS base

# Create non-root user
RUN groupadd --gid 1000 app && \
    useradd --uid 1000 --gid app --create-home app

WORKDIR /app

# Install Python dependencies (cache-friendly: only re-runs when pyproject.toml changes)
COPY pyproject.toml ./
RUN mkdir -p src/finlytics && touch src/finlytics/__init__.py && \
    pip install --no-cache-dir .

# Create writable dir for uploads BEFORE copying source,
# so this layer stays cached when only the app code changes.
RUN mkdir -p /app/data/uploads && chown -R app:app /app/data

# Copy full source and reinstall package (deps already cached).
# These are the only layers that change on a normal code update.
COPY src/ ./src/
RUN pip install --no-cache-dir --no-deps .

# Copy migration + seed artefacts (needed by the entrypoint)
COPY alembic.ini seed.py ./
COPY alembic/ ./alembic/

# Copy the compiled React SPA (pre-built on host: cd frontend && npm ci && npm run build)
COPY frontend/dist ./frontend/dist

# Entrypoint: runs migrations + seed → exec uvicorn
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN sed -i 's/\r$//' /docker-entrypoint.sh && chmod +x /docker-entrypoint.sh

EXPOSE 7777

USER app

ENTRYPOINT ["/docker-entrypoint.sh"]
