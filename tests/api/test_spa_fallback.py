"""Tests for the SPA catch-all route (app.py).

Verifies:
* GET to a non-API path (e.g. /settings) returns index.html when dist exists.
* GET to a nested client route (/settings/tags) also returns index.html.
* Real static assets (/assets/main.js) are served directly, not as index.html.
* Paths escaping frontend/dist (`..`, absolute, sibling-prefix) never serve the
  target file — they fall through to index.html.
* When frontend/dist is absent the catch-all returns a graceful 200/JSON.
* /health still returns its liveness JSON (not shadowed by the catch-all).
* /api/... routes return API JSON, not HTML (not shadowed by the catch-all).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from finlytics.api.deps import get_current_user, get_db
from finlytics.app import app, spa_fallback


@pytest.fixture
def dist_dir(tmp_path: Path) -> Path:
    """Fake frontend/dist with index.html and one static asset."""
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html><body>SPA</body></html>", encoding="utf-8")
    assets = dist / "assets"
    assets.mkdir()
    (assets / "main.js").write_text("console.log('spa')", encoding="utf-8")
    return dist


# ── SPA index.html fallback ───────────────────────────────────────────────────

async def test_settings_route_serves_index_html(dist_dir: Path) -> None:
    """GET /settings returns the SPA index.html so react-router can take over."""
    with patch("finlytics.app._SPA_DIR", dist_dir):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/settings")

    assert resp.status_code == 200
    assert "<html>" in resp.text


async def test_nested_spa_route_serves_index_html(dist_dir: Path) -> None:
    """GET /settings/tags (nested client route) also returns index.html."""
    with patch("finlytics.app._SPA_DIR", dist_dir):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/settings/tags")

    assert resp.status_code == 200
    assert "<html>" in resp.text


async def test_root_serves_index_html(dist_dir: Path) -> None:
    """GET / returns the SPA index.html."""
    with patch("finlytics.app._SPA_DIR", dist_dir):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/")

    assert resp.status_code == 200
    assert "<html>" in resp.text


# ── Real static assets served directly ───────────────────────────────────────

async def test_static_asset_served_directly(dist_dir: Path) -> None:
    """GET /assets/main.js serves the actual file, not index.html."""
    with patch("finlytics.app._SPA_DIR", dist_dir):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/assets/main.js")

    assert resp.status_code == 200
    assert "console.log" in resp.text
    assert "<html>" not in resp.text


# ── Traversal containment ────────────────────────────────────────────────────
#
# The handler is called directly: an HTTP client (and Starlette's router) would
# collapse `..` before it ever reaches `full_path`, which is exactly the input
# these tests need to exercise.

async def test_relative_traversal_falls_back_to_index(dist_dir: Path, tmp_path: Path) -> None:
    """`../secret.txt` escapes dist, so index.html is served instead of the file."""
    (tmp_path / "secret.txt").write_text("TOP SECRET", encoding="utf-8")

    with patch("finlytics.app._SPA_DIR", dist_dir):
        resp = await spa_fallback("../secret.txt")

    assert getattr(resp, "path", None) == str(dist_dir / "index.html")


async def test_absolute_path_falls_back_to_index(dist_dir: Path, tmp_path: Path) -> None:
    """An absolute path would make os.path.join discard the root — still contained."""
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP SECRET", encoding="utf-8")

    with patch("finlytics.app._SPA_DIR", dist_dir):
        resp = await spa_fallback(str(secret))

    assert getattr(resp, "path", None) == str(dist_dir / "index.html")


async def test_sibling_directory_sharing_prefix_is_rejected(tmp_path: Path) -> None:
    """`<root>-backup` shares the string prefix of `<root>` but is outside it."""
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html><body>SPA</body></html>", encoding="utf-8")
    sibling = tmp_path / "dist-backup"
    sibling.mkdir()
    (sibling / "secret.txt").write_text("TOP SECRET", encoding="utf-8")

    with patch("finlytics.app._SPA_DIR", dist):
        resp = await spa_fallback("../dist-backup/secret.txt")

    assert getattr(resp, "path", None) == str(dist / "index.html")


# ── Absent dist → graceful fallback ──────────────────────────────────────────

async def test_spa_absent_returns_graceful_json(tmp_path: Path) -> None:
    """When frontend/dist does not exist the catch-all returns a graceful 200/JSON."""
    nonexistent = tmp_path / "does_not_exist"
    with patch("finlytics.app._SPA_DIR", nonexistent):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/settings")

    assert resp.status_code == 200
    assert resp.json()["detail"] == "Frontend not available"


# ── Existing routes must NOT be shadowed ─────────────────────────────────────

async def test_health_not_shadowed_by_spa(dist_dir: Path) -> None:
    """GET /health returns the liveness JSON even when the SPA catch-all is active."""
    with patch("finlytics.app._SPA_DIR", dist_dir):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/health")

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_api_route_not_shadowed_by_spa(dist_dir: Path) -> None:
    """/api/tags returns API JSON (not the SPA index.html)."""
    mock_session = MagicMock()
    mock_session.execute = AsyncMock()
    mock_session.flush = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.close = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.begin = MagicMock(return_value=AsyncMock())

    async def _override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = lambda: MagicMock(username="testuser")
    try:
        with (
            patch("finlytics.app._SPA_DIR", dist_dir),
            patch("finlytics.db.queries.get_tags", new_callable=AsyncMock, return_value=[]),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.get("/api/tags")
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")
    assert resp.json() == []
    assert "<html>" not in resp.text
