#!/bin/sh
# Finlytics container entrypoint.
# Relies on compose depends_on + healthcheck to guarantee DB is ready before this runs.
set -e

echo "[entrypoint] Running DB migrations..."
alembic upgrade head

echo "[entrypoint] Seeding base categories..."
python seed.py

echo "[entrypoint] Starting Finlytics..."
exec python -m finlytics
