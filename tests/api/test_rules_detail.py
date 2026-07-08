"""Tests for Rule detail_mode / detail_value fields in the rules API."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from tests.api.test_rules import _make_rule, _VALID_BODY


# ── Create with detail_mode/detail_value ──────────────────────────────────────

async def test_create_rule_with_detail_fields(client):
    """POST /api/rules with detail_mode+detail_value returns both in RuleOut."""
    body = {
        **_VALID_BODY,
        "skip_ai": False,
        "detail_mode": "contains",
        "detail_value": "OCTOPUS ENERGY",
    }
    rule = _make_rule(
        skip_ai=False,
        set_category="Housing",
        detail_mode="contains",
        detail_value="OCTOPUS ENERGY",
    )
    with patch("finlytics.db.repository.create_rule", new_callable=AsyncMock) as mock:
        mock.return_value = rule
        resp = await client.post("/api/rules", json=body)

    assert resp.status_code == 201
    data = resp.json()
    assert data["detail_mode"] == "contains"
    assert data["detail_value"] == "OCTOPUS ENERGY"


async def test_create_rule_detail_null_by_default(client):
    """When detail_mode/detail_value are omitted, RuleOut returns null for both."""
    rule = _make_rule(skip_ai=False, detail_mode=None, detail_value=None)
    with patch("finlytics.db.repository.create_rule", new_callable=AsyncMock) as mock:
        mock.return_value = rule
        resp = await client.post("/api/rules", json={**_VALID_BODY, "skip_ai": False})

    assert resp.status_code == 201
    assert resp.json()["detail_mode"] is None
    assert resp.json()["detail_value"] is None


# ── Update with detail_mode/detail_value ──────────────────────────────────────

async def test_update_rule_sets_detail_fields(client):
    """PATCH /api/rules/{id} can set detail_mode and detail_value."""
    existing = _make_rule(skip_ai=False, detail_mode=None, detail_value=None)
    existing.detail_mode = "exact"
    existing.detail_value = "GCREOCTOPUSENERGY"

    with patch("finlytics.db.repository.get_rule", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = existing
        resp = await client.patch(
            "/api/rules/1",
            json={"detail_mode": "exact", "detail_value": "GCREOCTOPUSENERGY"},
        )

    assert resp.status_code == 200
    assert resp.json()["detail_mode"] == "exact"
    assert resp.json()["detail_value"] == "GCREOCTOPUSENERGY"


# ── Validation: mode-without-value and value-without-mode ────────────────────

async def test_create_rule_422_detail_mode_without_value(client):
    """detail_mode set without detail_value → 422."""
    body = {**_VALID_BODY, "skip_ai": False, "detail_mode": "contains"}
    resp = await client.post("/api/rules", json=body)

    assert resp.status_code == 422
    assert "detail_value" in resp.json()["detail"]


async def test_create_rule_422_detail_value_without_mode(client):
    """detail_value set without detail_mode → 422."""
    body = {**_VALID_BODY, "skip_ai": False, "detail_value": "some value"}
    resp = await client.post("/api/rules", json=body)

    assert resp.status_code == 422
    assert "detail_mode" in resp.json()["detail"]


# ── Validation: regex ─────────────────────────────────────────────────────────

async def test_create_rule_422_invalid_detail_regex(client):
    """detail_mode=regex with an invalid pattern → 422."""
    body = {
        **_VALID_BODY,
        "skip_ai": False,
        "detail_mode": "regex",
        "detail_value": "[unclosed",
    }
    resp = await client.post("/api/rules", json=body)

    assert resp.status_code == 422
    assert "regular expression" in resp.json()["detail"]


async def test_create_rule_valid_detail_regex_accepted(client):
    """A valid detail_mode=regex pattern passes validation."""
    body = {
        **_VALID_BODY,
        "skip_ai": False,
        "detail_mode": "regex",
        "detail_value": r"OCTOPUS\s+ENERGY",
    }
    rule = _make_rule(skip_ai=False, detail_mode="regex", detail_value=r"OCTOPUS\s+ENERGY")
    with patch("finlytics.db.repository.create_rule", new_callable=AsyncMock) as mock:
        mock.return_value = rule
        resp = await client.post("/api/rules", json=body)

    assert resp.status_code == 201


async def test_update_rule_422_detail_mode_without_value(client):
    """PATCH resulting in detail_mode set but detail_value null → 422."""
    existing = _make_rule(skip_ai=False, detail_mode=None, detail_value=None)

    with patch("finlytics.db.repository.get_rule", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = existing
        resp = await client.patch(
            "/api/rules/1",
            json={"detail_mode": "starts_with"},
        )

    assert resp.status_code == 422
    assert "detail_value" in resp.json()["detail"]


async def test_update_rule_422_detail_value_without_mode(client):
    """PATCH resulting in detail_value set but detail_mode null → 422."""
    existing = _make_rule(skip_ai=False, detail_mode=None, detail_value=None)

    with patch("finlytics.db.repository.get_rule", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = existing
        resp = await client.patch(
            "/api/rules/1",
            json={"detail_value": "OCTOPUS"},
        )

    assert resp.status_code == 422
    assert "detail_mode" in resp.json()["detail"]
