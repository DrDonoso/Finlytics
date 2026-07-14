"""Tests for GET /api/investments/plugins endpoint.

Static registry — no DB access, no LLM.  Uses:
  * ``unauthenticated_client`` (local): only get_db overridden so the real
    get_current_user dependency enforces the 401 on missing cookie.
  * ``client`` (conftest): get_current_user pre-bypassed, for all 200 cases.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from finlytics.api.deps import get_db
from finlytics.app import app

_EXPECTED_IDS = {"indexa-capital", "generic-broker", "crypto-exchange"}
_REQUIRED_KEYS = {"id", "name", "description", "icon", "status", "auth_type", "supported_features"}


# ── Fixture for unauthenticated requests ─────────────────────────────────────

@pytest.fixture
async def unauthenticated_client():
    """Client with only get_db overridden; get_current_user runs for real.

    Sending no session cookie causes it to raise 401 before any DB touch.
    """
    mock_session = MagicMock()
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.close = AsyncMock()
    begin_cm = AsyncMock()
    mock_session.begin = MagicMock(return_value=begin_cm)

    async def _override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = _override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


# ── Auth guard ────────────────────────────────────────────────────────────────

async def test_plugins_401_unauthenticated(unauthenticated_client):
    """No session cookie → 401 before the registry is ever consulted."""
    resp = await unauthenticated_client.get("/api/investments/plugins")
    assert resp.status_code == 401


# ── Shape & content (authenticated via conftest ``client`` fixture) ───────────

async def test_plugins_200_returns_list_of_three(client):
    """Authenticated request → 200, exactly 3 plugins."""
    resp = await client.get("/api/investments/plugins")
    assert resp.status_code == 200
    assert len(resp.json()) == 3


async def test_plugins_all_required_keys_present(client):
    """Every plugin object carries all required keys."""
    resp = await client.get("/api/investments/plugins")
    for plugin in resp.json():
        missing = _REQUIRED_KEYS - plugin.keys()
        assert not missing, f"Plugin '{plugin.get('id')}' is missing keys: {missing}"


async def test_plugins_all_status_coming_soon(client):
    """All plugins report status == 'coming_soon' (phase 1 contract)."""
    resp = await client.get("/api/investments/plugins")
    for plugin in resp.json():
        assert plugin["status"] == "coming_soon", (
            f"Plugin '{plugin['id']}' has unexpected status '{plugin['status']}'"
        )


async def test_plugins_correct_id_set(client):
    """Returned id set matches the three expected plugin identifiers exactly."""
    resp = await client.get("/api/investments/plugins")
    ids = {p["id"] for p in resp.json()}
    assert ids == _EXPECTED_IDS


async def test_plugins_supported_features_nonempty(client):
    """Every plugin exposes a non-empty supported_features list."""
    resp = await client.get("/api/investments/plugins")
    for plugin in resp.json():
        features = plugin["supported_features"]
        assert isinstance(features, list), f"Plugin '{plugin['id']}': features not a list"
        assert len(features) > 0, f"Plugin '{plugin['id']}': supported_features is empty"
