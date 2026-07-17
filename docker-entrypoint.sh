#!/bin/sh
# Finlytics container entrypoint.
# Relies on compose depends_on + healthcheck to guarantee DB is ready before this runs.
set -e

echo "$(date '+%Y-%m-%d %H:%M:%S') [entrypoint] Running DB migrations..."
alembic upgrade head

echo "$(date '+%Y-%m-%d %H:%M:%S') [entrypoint] Seeding base categories..."
python seed.py

echo "$(date '+%Y-%m-%d %H:%M:%S') [entrypoint] Starting Finlytics..."
exec python -m finlytics
