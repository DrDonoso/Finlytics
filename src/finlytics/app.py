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

  /{full_path:path}       — React SPA catch-all (GET only; registered AFTER /api)
                            Serves frontend/dist/<path> when the file exists;
                            otherwise serves frontend/dist/index.html so
                            react-router handles client-side routes like /settings.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.responses import FileResponse, JSONResponse, Response

from finlytics.api.accounts import router as accounts_router
from finlytics.api.auth import router as auth_router
from finlytics.api.backup import router as backup_router
from finlytics.api.categories import router as categories_router
from finlytics.api.deps import get_current_user
from finlytics.api.fidelity import router as fidelity_router
from finlytics.api.imports import router as imports_router
from finlytics.api.investments import router as investments_router
from finlytics.api.rules import router as rules_router
from finlytics.api.statements import router as statements_router
from finlytics.api.summary import router as summary_router
from finlytics.api.tags import router as tags_router
from finlytics.api.transactions import router as transactions_router

log = logging.getLogger(__name__)

app = FastAPI(
    title="Finlytics",
    version="0.1.0",
    description="Personal bank-account expense tracking with AI-powered extraction",
)

# ── Auth router (PUBLIC — no auth dependency) ─────────────────────────────────
# Must be registered before the data routers so /api/auth/* routes are matched
# without going through get_current_user.
app.include_router(auth_router, prefix="/api")

# ── Protected data routers ────────────────────────────────────────────────────
_auth = [Depends(get_current_user)]

app.include_router(accounts_router,     prefix="/api", dependencies=_auth)
app.include_router(backup_router,       prefix="/api", dependencies=_auth)
app.include_router(categories_router,   prefix="/api", dependencies=_auth)
app.include_router(rules_router,        prefix="/api", dependencies=_auth)
app.include_router(statements_router,   prefix="/api", dependencies=_auth)
app.include_router(tags_router,         prefix="/api", dependencies=_auth)
app.include_router(transactions_router, prefix="/api", dependencies=_auth)
app.include_router(summary_router,      prefix="/api", dependencies=_auth)
app.include_router(imports_router,      prefix="/api", dependencies=_auth)
app.include_router(investments_router,  prefix="/api", dependencies=_auth)
app.include_router(fidelity_router,     prefix="/api", dependencies=_auth)


@app.get("/health", tags=["health"])
async def health() -> dict:
    return {"status": "ok"}


# ── React SPA catch-all (optional — API works without it) ─────────────────────
# Registered AFTER all /api routes so it never shadows them.
_SPA_DIR = Path("frontend/dist")


@app.get("/{full_path:path}", include_in_schema=False)
async def spa_fallback(full_path: str) -> Response:
    """Serve the React SPA for any non-API GET request.

    * Real static assets (JS, CSS, images) are served directly from frontend/dist.
    * All other paths return index.html so react-router handles client-side routing.
    * When frontend/dist doesn't exist (dev/test), returns a minimal JSON 200.
    """
    if _SPA_DIR.is_dir():
        spa_root = _SPA_DIR.resolve()
        candidate = (spa_root / full_path).resolve()
        if candidate.is_file() and candidate.is_relative_to(spa_root):
            return FileResponse(candidate)
        index = spa_root / "index.html"
        if index.is_file():
            return FileResponse(index)
    return JSONResponse({"detail": "Frontend not available"})

