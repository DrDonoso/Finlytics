"""Tests for GET /api/version."""

from __future__ import annotations

import pytest


# ── happy-path ────────────────────────────────────────────────────────────────

async def test_version_basic_shape(client):
    """Endpoint returns 200 with correct keys and a non-empty version string."""
    resp = await client.get("/api/version")

    assert resp.status_code == 200
    data = resp.json()
    assert set(data.keys()) == {"version", "image_tag", "built_at"}
    assert isinstance(data["version"], str)
    assert data["version"]  # not empty


async def test_version_nulls_without_env(client, monkeypatch):
    """image_tag and built_at are null when the env vars are absent."""
    monkeypatch.delenv("FINLYTICS_IMAGE_TAG", raising=False)
    monkeypatch.delenv("FINLYTICS_BUILD_DATE", raising=False)

    resp = await client.get("/api/version")

    assert resp.status_code == 200
    data = resp.json()
    assert data["image_tag"] is None
    assert data["built_at"] is None


async def test_version_env_vars_propagated(client, monkeypatch):
    """image_tag and built_at are populated when env vars are set."""
    monkeypatch.setenv("FINLYTICS_IMAGE_TAG", "20260716")
    monkeypatch.setenv("FINLYTICS_BUILD_DATE", "2026-07-16T08:10:24+02:00")

    resp = await client.get("/api/version")

    assert resp.status_code == 200
    data = resp.json()
    assert data["image_tag"] == "20260716"
    assert data["built_at"] == "2026-07-16T08:10:24+02:00"


# ── auth guard ────────────────────────────────────────────────────────────────

async def test_version_requires_auth():
    """Endpoint returns 401 when no session cookie is provided."""
    from httpx import ASGITransport, AsyncClient

    from finlytics.app import app

    # Use a client without the get_current_user override so the real guard runs.
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/version")

    assert resp.status_code == 401


# ── _read_version unit tests ──────────────────────────────────────────────────

def test_read_version_returns_string():
    from finlytics.api.version import _read_version

    v = _read_version()
    assert isinstance(v, str)
    assert v  # not empty


def test_read_version_fallback_when_not_installed(monkeypatch):
    """When importlib.metadata raises PackageNotFoundError, falls back gracefully."""
    from importlib.metadata import PackageNotFoundError

    import finlytics.api.version as version_mod

    monkeypatch.setattr(version_mod, "_pkg_version", lambda _: (_ for _ in ()).throw(PackageNotFoundError("finlytics")))  # type: ignore[arg-type]

    v = version_mod._read_version()
    assert isinstance(v, str)
    assert v  # "0.1.0" or whatever pyproject says
