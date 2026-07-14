"""Shared fixtures for API tests.

Strategy
────────
* The DB session dependency (get_db) is overridden with a carefully configured
  mock so no live PostgreSQL is needed.
* session.begin() returns an AsyncMock that works as an async context manager
  (AsyncMock supports __aenter__/__aexit__ by default in Python 3.8+).
* Query functions in finlytics.db.queries are patched per-test with canned
  return values to test routing + serialisation in isolation.
* The LLM client dependency (get_llm_client) is overridden with a plain Mock
  when tests don't exercise the LLM path.
* get_current_user is overridden to always return a mock user so that the
  router-level auth dependency doesn't interfere with non-auth tests.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from finlytics.api.deps import get_current_user, get_db, get_llm_client
from finlytics.app import app


@pytest.fixture
def mock_session() -> MagicMock:
    """A mock standing in for the SQLAlchemy AsyncSession.

    * execute, flush, commit, close → AsyncMock (need await)
    * add → MagicMock (synchronous in SQLAlchemy 2)
    * begin() → returns an AsyncMock that works as an async context manager
    """
    session = MagicMock()
    session.execute = AsyncMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.close = AsyncMock()
    session.add = MagicMock()
    session.scalar = AsyncMock(return_value=0)   # needed by GET /investments/plugins

    # session.begin() must be usable as `async with session.begin():`
    # AsyncMock() supports the async context manager protocol out of the box.
    begin_cm = AsyncMock()
    session.begin = MagicMock(return_value=begin_cm)
    return session


@pytest.fixture
async def client(mock_session: MagicMock) -> AsyncClient:
    """ASGI test client with DB session + auth overridden (no live Postgres)."""
    async def _override_get_db():
        yield mock_session

    async def _override_get_current_user():
        return MagicMock(username="testuser")

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = _override_get_current_user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
async def client_with_llm(mock_session: MagicMock):
    """ASGI test client with DB session, auth, and LLM client overridden."""
    mock_llm = AsyncMock()

    async def _override_get_db():
        yield mock_session

    def _override_get_llm():
        return mock_llm

    async def _override_get_current_user():
        return MagicMock(username="testuser")

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_llm_client] = _override_get_llm
    app.dependency_overrides[get_current_user] = _override_get_current_user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c, mock_llm
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_llm_client, None)
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
async def client_no_llm(mock_session: MagicMock) -> AsyncClient:
    """ASGI test client where get_llm_client is wired to always raise 503.

    Use this instead of the bare ``client`` fixture when testing the 503 path
    for LLM-required endpoints, so the test doesn't depend on whether env vars
    are configured in the current environment.
    """
    async def _override_get_db():
        yield mock_session

    def _raise_503():
        raise HTTPException(status_code=503, detail="LLM not configured")

    async def _override_get_current_user():
        return MagicMock(username="testuser")

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_llm_client] = _raise_503
    app.dependency_overrides[get_current_user] = _override_get_current_user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_llm_client, None)
    app.dependency_overrides.pop(get_current_user, None)
