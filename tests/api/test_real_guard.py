"""Regression tests: real get_current_user guard (no override).

These tests do NOT override get_current_user in dependency_overrides.
They exercise the full auth dependency — cookie validation + DB user lookup —
alongside a protected write path that calls ``async with session.begin()``.

Background on the bug they guard against
─────────────────────────────────────────
Before the fix, ``get_current_user`` took ``db: AsyncSession = Depends(get_db)``
and called ``await db.scalar(select(User)...)``.  That scalar triggers SQLAlchemy
async *autobegin*, leaving an ACTIVE transaction on the shared request session.
When the endpoint then calls ``async with session.begin()``, SQLAlchemy raises:

    InvalidRequestError: A transaction is already begun on this Session.

The fix: ``get_current_user`` opens its OWN short-lived session via
``async_session_factory()``, keeping the request session pristine for
``session.begin()`` calls inside write handlers.

These tests would have caught that bug because they run the real guard
AND exercise a write path.  The existing test suite bypassed the guard via
``dependency_overrides[get_current_user]``, so the conflict was invisible.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from finlytics.api.deps import get_db
from finlytics.app import app
from finlytics.auth.security import create_token
from finlytics.db.models import User


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_auth_factory(username: str = "drdonoso") -> MagicMock:
    """Return a mock for async_session_factory usable by get_current_user.

    Calling the factory returns an async context manager that yields a session
    whose ``.scalar()`` returns a fake User.
    """
    user = MagicMock(spec=User)
    user.username = username

    auth_session = MagicMock()
    auth_session.scalar = AsyncMock(return_value=user)
    auth_session.__aenter__ = AsyncMock(return_value=auth_session)
    auth_session.__aexit__ = AsyncMock(return_value=False)

    return MagicMock(return_value=auth_session)


@pytest.fixture
def request_session() -> MagicMock:
    """Mock for the endpoint's request session (get_db).

    Supports ``session.begin()`` as an async context manager — exactly what the
    real write handlers (update_transaction, create_tag, …) use.
    """
    session = MagicMock()
    session.execute = AsyncMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.close = AsyncMock()
    session.scalar = AsyncMock()
    session.add = MagicMock()
    begin_cm = AsyncMock()
    session.begin = MagicMock(return_value=begin_cm)
    return session


_TX = {
    "id": 1,
    "transaction_date": "2024-06-01",
    "amount": -42.5,
    "currency": "EUR",
    "description": "MERCADONA",
    "category": "Groceries",
    "account": "BBVA",
    "category_confidence": 0.97,
    "balance_after": 1200.0,
    "tags": [],
    "merchant": "Mercadona S.A.",
}

_TAG = {"id": 10, "name": "alimentación", "color": "#10b981", "emoji": "🛒", "tx_count": 0}


# ── PATCH /api/transactions/{id} — real guard + write path ───────────────────

async def test_real_guard_patch_transaction_succeeds(request_session: MagicMock):
    """REGRESSION: get_current_user must not autobegin the request session.

    Real guard runs (no override). The auth lookup uses its own session.
    The endpoint's ``async with session.begin()`` must not raise
    InvalidRequestError.  HTTP 200 + persisted merchant value expected.
    """
    token = create_token("drdonoso")
    auth_factory = _make_auth_factory("drdonoso")

    async def _override_get_db():
        yield request_session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            with patch("finlytics.api.deps.async_session_factory", auth_factory):
                with patch("finlytics.db.queries.update_transaction", new_callable=AsyncMock) as mock_update:
                    mock_update.return_value = {**_TX, "merchant": "Mercadona S.A."}
                    resp = await client.patch(
                        "/api/transactions/1",
                        json={"merchant": "Mercadona S.A."},
                        cookies={"finlytics_session": token},
                    )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 200
    assert resp.json()["merchant"] == "Mercadona S.A."


async def test_real_guard_patch_transaction_no_cookie_is_401(request_session: MagicMock):
    """Real guard: missing cookie returns 401 before any DB access."""
    async def _override_get_db():
        yield request_session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.patch(
                "/api/transactions/1",
                json={"merchant": "x"},
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 401


# ── POST /api/tags — real guard + write path ──────────────────────────────────

async def test_real_guard_create_tag_succeeds(request_session: MagicMock):
    """REGRESSION: create_tag also calls session.begin() — same guard required.

    Confirms the fix covers every auth-protected write path, not just transactions.
    """
    token = create_token("drdonoso")
    auth_factory = _make_auth_factory("drdonoso")

    async def _override_get_db():
        yield request_session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            with patch("finlytics.api.deps.async_session_factory", auth_factory):
                with patch("finlytics.db.queries.create_tag", new_callable=AsyncMock) as mock_create:
                    mock_create.return_value = _TAG
                    resp = await client.post(
                        "/api/tags",
                        json={"name": "🛒 alimentación", "color": "#10b981"},
                        cookies={"finlytics_session": token},
                    )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 201
    assert resp.json()["name"] == "alimentación"
