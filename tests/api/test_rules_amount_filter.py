"""Tests for Rule amount_min / amount_max fields in the rules API."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from tests.api.test_rules import _make_rule, _VALID_BODY


# ── Create with amount_min / amount_max ───────────────────────────────────────


async def test_create_rule_with_amount_min_and_max(client):
    """POST /api/rules with amount_min+amount_max returns both in RuleOut."""
    body = {
        **_VALID_BODY,
        "skip_ai": False,
        "amount_min": 100.0,
        "amount_max": 500.0,
    }
    rule = _make_rule(skip_ai=False, amount_min=100.0, amount_max=500.0)
    with patch("finlytics.db.repository.create_rule", new_callable=AsyncMock) as mock:
        mock.return_value = rule
        resp = await client.post("/api/rules", json=body)

    assert resp.status_code == 201
    data = resp.json()
    assert data["amount_min"] == 100.0
    assert data["amount_max"] == 500.0


async def test_create_rule_with_amount_min_only(client):
    """POST /api/rules with only amount_min — amount_max stays null."""
    body = {**_VALID_BODY, "skip_ai": False, "amount_min": 50.0}
    rule = _make_rule(skip_ai=False, amount_min=50.0, amount_max=None)
    with patch("finlytics.db.repository.create_rule", new_callable=AsyncMock) as mock:
        mock.return_value = rule
        resp = await client.post("/api/rules", json=body)

    assert resp.status_code == 201
    assert resp.json()["amount_min"] == 50.0
    assert resp.json()["amount_max"] is None


async def test_rule_out_amount_min_max_null_by_default(client):
    """When amount_min/amount_max are omitted, RuleOut returns null for both."""
    rule = _make_rule(skip_ai=False, amount_min=None, amount_max=None)
    with patch("finlytics.db.repository.create_rule", new_callable=AsyncMock) as mock:
        mock.return_value = rule
        resp = await client.post("/api/rules", json={**_VALID_BODY, "skip_ai": False})

    assert resp.status_code == 201
    assert resp.json()["amount_min"] is None
    assert resp.json()["amount_max"] is None


# ── Update with amount_min / amount_max ───────────────────────────────────────


async def test_update_rule_sets_amount_min(client):
    """PATCH /api/rules/{id} can set amount_min."""
    existing = _make_rule(skip_ai=False, amount_min=None, amount_max=None)
    existing.amount_min = 200.0

    with patch("finlytics.db.repository.get_rule", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = existing
        resp = await client.patch("/api/rules/1", json={"amount_min": 200.0})

    assert resp.status_code == 200
    assert resp.json()["amount_min"] == 200.0


async def test_update_rule_sets_both_bounds(client):
    """PATCH /api/rules/{id} can set both amount_min and amount_max."""
    existing = _make_rule(skip_ai=False, amount_min=None, amount_max=None)
    existing.amount_min = 10.0
    existing.amount_max = 1000.0

    with patch("finlytics.db.repository.get_rule", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = existing
        resp = await client.patch(
            "/api/rules/1",
            json={"amount_min": 10.0, "amount_max": 1000.0},
        )

    assert resp.status_code == 200
    assert resp.json()["amount_min"] == 10.0
    assert resp.json()["amount_max"] == 1000.0


# ── Validation: negative values rejected ─────────────────────────────────────


async def test_create_rule_422_negative_amount_min(client):
    """amount_min < 0 → 422."""
    body = {**_VALID_BODY, "skip_ai": False, "amount_min": -10.0}
    resp = await client.post("/api/rules", json=body)

    assert resp.status_code == 422
    assert "amount_min" in resp.json()["detail"]


async def test_create_rule_422_negative_amount_max(client):
    """amount_max < 0 → 422."""
    body = {**_VALID_BODY, "skip_ai": False, "amount_max": -5.0}
    resp = await client.post("/api/rules", json=body)

    assert resp.status_code == 422
    assert "amount_max" in resp.json()["detail"]


# ── Validation: min > max rejected ────────────────────────────────────────────


async def test_create_rule_422_min_greater_than_max(client):
    """amount_min > amount_max → 422."""
    body = {**_VALID_BODY, "skip_ai": False, "amount_min": 500.0, "amount_max": 100.0}
    resp = await client.post("/api/rules", json=body)

    assert resp.status_code == 422
    assert "amount_min" in resp.json()["detail"]


async def test_update_rule_422_resulting_min_greater_than_max(client):
    """PATCH that results in amount_min > amount_max (via effective merge) → 422."""
    # Existing rule has amount_max=100; update sets amount_min=200 → 200 > 100
    existing = _make_rule(skip_ai=False, amount_min=None, amount_max=100.0)

    with patch("finlytics.db.repository.get_rule", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = existing
        resp = await client.patch("/api/rules/1", json={"amount_min": 200.0})

    assert resp.status_code == 422
    assert "amount_min" in resp.json()["detail"]


async def test_create_rule_zero_amount_min_valid(client):
    """amount_min=0 is a valid lower bound (>= 0)."""
    body = {**_VALID_BODY, "skip_ai": False, "amount_min": 0.0}
    rule = _make_rule(skip_ai=False, amount_min=0.0, amount_max=None)
    with patch("finlytics.db.repository.create_rule", new_callable=AsyncMock) as mock:
        mock.return_value = rule
        resp = await client.post("/api/rules", json=body)

    assert resp.status_code == 201
