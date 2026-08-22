"""Finlytics FastAPI application.

Route layout:
  GET  /health            — liveness probe (no DB)

  ── Auth (PUBLIC) ────────────────────────────────────────────────────────────
  GET  /api/auth/status   — initialized + authenticated flags
  POST /api/auth/setup    — first-run user creation (self-disabling)
  POST /api/auth/login    — credential verification, sets session cookie
  POST /api/auth/logout   — clears session cookie (idempotent)
  GET  /api/auth/me       — returns username (PROTECTED)

  ── Data (PROTECTED — require valid session cookie) ──────────────────────────
  /api/accounts           — list bank/broker accounts
  /api/categories         — list spending categories
  /api/transactions       — paginated transaction ledger
  /api/summary/overview   — total expense/income/net + top category
  /api/summary/by-category
  /api/summary/by-month
  /api/summary/by-account
  GET  /api/statements/months               — months with ≥1 transaction (DESC)
  DELETE /api/statements/month?year&month   — hard-delete a month's transactions
  POST /api/imports       — upload statement → parse → LLM extract → persist
  GET  /api/version       — app version + optional build metadata (PROTECTED)
  /api/notifications      — notification list, badge count, read/dismiss
  /api/assistant          — finance chat assistant (SSE streaming, read-only tools)
  /api/mortgages          — mortgage CRUD, amortization schedule, prepayment simulator

  /{full_path:path}       — React SPA catch-all (GET only; registered AFTER /api)
                            Serves frontend/dist/<path> when the file exists;
                            otherwise serves frontend/dist/index.html so
                            react-router handles client-side routes like /settings.
"""

from __future__ import annotations

import asyncio
import logging
import mimetypes
import os
import sys
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.responses import FileResponse, JSONResponse, Response

from finlytics.api.accounts import router as accounts_router
from finlytics.api.assistant import router as assistant_router
from finlytics.api.auth import router as auth_router
from finlytics.api.backup import router as backup_router
from finlytics.api.categories import router as categories_router
from finlytics.api.deps import get_current_user
from finlytics.api.fidelity import router as fidelity_router
from finlytics.api.imports import router as imports_router
from finlytics.api.investments import router as investments_router
from finlytics.api.mortgage import router as mortgage_router
from finlytics.api.notifications import router as notifications_router
from finlytics.api.rules import router as rules_router
from finlytics.api.statements import router as statements_router
from finlytics.api.summary import router as summary_router
from finlytics.api.tags import router as tags_router
from finlytics.api.transactions import router as transactions_router
from finlytics.api.version import router as version_router

log = logging.getLogger(__name__)


# ── Background notifications loop ─────────────────────────────────────────────

async def _notifications_loop() -> None:
    """Periodically evaluate detectors and upsert notifications for all users.

    Runs as a background asyncio.Task started in the lifespan hook.
    Wraps each iteration in try/except so a single failure never kills the
    loop.  Cancelled cleanly on application shutdown.
    """
    from sqlalchemy import select

    from finlytics.clock import today as local_today
    from finlytics.db.models import User
    from finlytics.db.session import async_session_factory
    from finlytics.notifications.service import (
        EVAL_INTERVAL_SECONDS,
        evaluate_notifications,
    )

    interval = EVAL_INTERVAL_SECONDS
    log.info("Notification loop started (interval=%ds)", interval)

    while True:
        # Measured from the start of the iteration: sleeping the full interval
        # AFTER the work would make the real period interval + duration, so the
        # evaluation would drift a little later on every lap.
        started = asyncio.get_running_loop().time()

        try:
            # Fetch all users in a short-lived session
            async with async_session_factory() as db:
                result = await db.execute(select(User))
                users = result.scalars().all()

            today = local_today()
            for user in users:
                try:
                    async with async_session_factory() as db:
                        await evaluate_notifications(db, user.id, today=today)
                except Exception:
                    log.exception(
                        "Notification evaluation failed for user_id=%d", user.id
                    )
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Notification loop iteration failed (non-fatal)")

        elapsed = asyncio.get_running_loop().time() - started
        await asyncio.sleep(max(0.0, interval - elapsed))


@asynccontextmanager
async def lifespan(app_: FastAPI):
    """Application lifespan: start/stop the background notifications loop."""
    _task: asyncio.Task | None = None

    # Guard: never run the loop inside pytest (no real DB; httpx may trigger
    # lifespan in newer versions).
    _in_test = "pytest" in sys.modules

    # The loop lives inside the web process, so starting the application with
    # several uvicorn workers would run it once per worker: every notification
    # would be evaluated N times and the user would receive N Telegram messages.
    # The entrypoint starts a single worker, but the loop cannot take that for
    # granted, so it warns in the log instead of failing silently the day
    # someone scales the service.
    if not _in_test:
        workers = os.environ.get("WEB_CONCURRENCY") or os.environ.get("UVICORN_WORKERS")
        if workers and workers.isdigit() and int(workers) > 1:
            log.warning(
                "Notification loop running with %s workers: notifications will be "
                "evaluated once per worker and delivered multiple times. Run a "
                "single worker, or move the loop to a dedicated process.",
                workers,
            )
        _task = asyncio.create_task(_notifications_loop())

    yield  # ← application is running here

    if _task is not None:
        _task.cancel()
        with suppress(asyncio.CancelledError):
            await _task
        log.info("Notification loop stopped")


# ── Application factory ───────────────────────────────────────────────────────

app = FastAPI(
    title="Finlytics",
    version="0.1.0",
    description="Personal bank-account expense tracking with AI-powered extraction",
    lifespan=lifespan,
)

# ── Auth router (PUBLIC — no auth dependency) ─────────────────────────────────
# Must be registered before the data routers so /api/auth/* routes are matched
# without going through get_current_user.
app.include_router(auth_router, prefix="/api")

# ── Protected data routers ────────────────────────────────────────────────────
_auth = [Depends(get_current_user)]

app.include_router(accounts_router,      prefix="/api", dependencies=_auth)
app.include_router(assistant_router,     prefix="/api", dependencies=_auth)
app.include_router(backup_router,        prefix="/api", dependencies=_auth)
app.include_router(categories_router,    prefix="/api", dependencies=_auth)
app.include_router(rules_router,         prefix="/api", dependencies=_auth)
app.include_router(statements_router,    prefix="/api", dependencies=_auth)
app.include_router(tags_router,          prefix="/api", dependencies=_auth)
app.include_router(transactions_router,  prefix="/api", dependencies=_auth)
app.include_router(summary_router,       prefix="/api", dependencies=_auth)
app.include_router(imports_router,       prefix="/api", dependencies=_auth)
app.include_router(investments_router,   prefix="/api", dependencies=_auth)
app.include_router(fidelity_router,      prefix="/api", dependencies=_auth)
app.include_router(mortgage_router,      prefix="/api", dependencies=_auth)
app.include_router(notifications_router, prefix="/api", dependencies=_auth)
app.include_router(version_router,       prefix="/api", dependencies=_auth)


@app.get("/health", tags=["health"])
async def health() -> dict:
    return {"status": "ok"}


# ── React SPA catch-all (optional — API works without it) ─────────────────────
# Registered AFTER all /api routes so it never shadows them.
_SPA_DIR = Path("frontend/dist")

# Python's mimetypes table has no entry for .webmanifest, so FileResponse would
# fall back to text/plain for the PWA manifest.
mimetypes.add_type("application/manifest+json", ".webmanifest")


@app.get("/{full_path:path}", include_in_schema=False)
async def spa_fallback(full_path: str) -> Response:
    """Serve the React SPA for any non-API GET request.

    * Real static assets (JS, CSS, images) are served directly from frontend/dist.
    * All other paths return index.html so react-router handles client-side routing.
    * Paths escaping frontend/dist (`..`, absolute paths, symlinks) never reach
      FileResponse — they fall through to index.html like any unknown route.
    * When frontend/dist doesn't exist (dev/test), returns a minimal JSON 200.
    """
    if _SPA_DIR.is_dir():
        spa_root = os.path.realpath(_SPA_DIR)
        # `full_path` is whatever the client typed: it may hold `..` segments, or
        # be absolute — in which case join() discards spa_root entirely. Resolve
        # first so `..` and symlinks collapse, then test containment on the
        # *resolved* path; testing before resolving would check a path that is
        # not the one eventually opened.
        candidate = os.path.realpath(os.path.join(spa_root, full_path))
        # The trailing separator is load-bearing: without it a sibling directory
        # such as `<root>-backup` shares the prefix and would pass the check.
        if candidate.startswith(spa_root + os.sep) and os.path.isfile(candidate):
            return FileResponse(candidate)
        index = os.path.join(spa_root, "index.html")
        if os.path.isfile(index):
            return FileResponse(index)
    return JSONResponse({"detail": "Frontend not available"})

