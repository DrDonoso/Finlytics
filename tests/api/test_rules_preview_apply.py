"""Tests for POST /api/rules/preview, /api/rules/apply, and /api/rules/{id}/apply."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Shared helpers ─────────────────────────────────────────────────────────────

_PREVIEW_BODY = {
    "name": "Mercadona",
    "description_mode": "contains",
    "description_value": "mercadona",
    "set_category": "Groceries",
    "skip_ai": False,
}

_APPLY_BODY = {
    "name": "Mercadona",
    "description_mode": "contains",
    "description_value": "mercadona",
    "set_category": "Groceries",
    "set_merchant": "Mercadona",
    "add_tags": ["supermercado"],
    "skip_ai": False,
}


def _make_rule(rule_id: int = 1, **overrides):
    """Return a MagicMock Rule ORM object with defaults suitable for apply tests."""
    rule = MagicMock()
    rule.id = rule_id
    rule.name = overrides.get("name", "Mercadona")
    rule.priority = overrides.get("priority", 100)
    rule.enabled = overrides.get("enabled", True)
    rule.description_mode = overrides.get("description_mode", "contains")
    rule.description_value = overrides.get("description_value", "mercadona")
    rule.amount_sign = overrides.get("amount_sign", None)
    rule.amount_min = overrides.get("amount_min", None)
    rule.amount_max = overrides.get("amount_max", None)
    rule.account_ref = overrides.get("account_ref", None)
    rule.currency = overrides.get("currency", None)
    rule.detail_mode = overrides.get("detail_mode", None)
    rule.detail_value = overrides.get("detail_value", None)
    rule.set_category = overrides.get("set_category", "Groceries")
    rule.set_merchant = overrides.get("set_merchant", "Mercadona")
    rule.add_tags = overrides.get("add_tags", [])
    rule.skip_ai = overrides.get("skip_ai", False)
    return rule


# ── POST /api/rules/preview ────────────────────────────────────────────────────

async def test_preview_returns_200(client):
    with patch("finlytics.api.rules._count_matching", new_callable=AsyncMock) as mock:
        mock.return_value = 5
        resp = await client.post("/api/rules/preview", json=_PREVIEW_BODY)

    assert resp.status_code == 200


async def test_preview_returns_count(client):
    with patch("finlytics.api.rules._count_matching", new_callable=AsyncMock) as mock:
        mock.return_value = 5
        resp = await client.post("/api/rules/preview", json=_PREVIEW_BODY)

    assert resp.json() == {"count": 5}


async def test_preview_zero_matches(client):
    with patch("finlytics.api.rules._count_matching", new_callable=AsyncMock) as mock:
        mock.return_value = 0
        resp = await client.post("/api/rules/preview", json=_PREVIEW_BODY)

    assert resp.status_code == 200
    assert resp.json()["count"] == 0


async def test_preview_invalid_body_missing_required(client):
    """Body missing description_mode should return 422 from Pydantic validation."""
    resp = await client.post("/api/rules/preview", json={"name": "x", "description_value": "y"})

    assert resp.status_code == 422


# ── POST /api/rules/apply ──────────────────────────────────────────────────────

async def test_apply_returns_200(client):
    with patch("finlytics.api.rules._apply_to_transactions", new_callable=AsyncMock) as mock:
        mock.return_value = 3
        resp = await client.post("/api/rules/apply", json=_APPLY_BODY)

    assert resp.status_code == 200


async def test_apply_returns_applied_count(client):
    with patch("finlytics.api.rules._apply_to_transactions", new_callable=AsyncMock) as mock:
        mock.return_value = 3
        resp = await client.post("/api/rules/apply", json=_APPLY_BODY)

    assert resp.json() == {"applied": 3}


async def test_apply_zero_matched(client):
    with patch("finlytics.api.rules._apply_to_transactions", new_callable=AsyncMock) as mock:
        mock.return_value = 0
        resp = await client.post("/api/rules/apply", json=_APPLY_BODY)

    assert resp.status_code == 200
    assert resp.json()["applied"] == 0


# ── POST /api/rules/{id}/apply ─────────────────────────────────────────────────

async def test_apply_saved_rule_returns_200(client):
    with (
        patch("finlytics.db.repository.get_rule", new_callable=AsyncMock) as get_mock,
        patch("finlytics.api.rules._apply_to_transactions", new_callable=AsyncMock) as apply_mock,
    ):
        get_mock.return_value = _make_rule(1)
        apply_mock.return_value = 7
        resp = await client.post("/api/rules/1/apply")

    assert resp.status_code == 200


async def test_apply_saved_rule_returns_applied_count(client):
    with (
        patch("finlytics.db.repository.get_rule", new_callable=AsyncMock) as get_mock,
        patch("finlytics.api.rules._apply_to_transactions", new_callable=AsyncMock) as apply_mock,
    ):
        get_mock.return_value = _make_rule(1)
        apply_mock.return_value = 7
        resp = await client.post("/api/rules/1/apply")

    assert resp.json() == {"applied": 7}


async def test_apply_saved_rule_404(client):
    with patch("finlytics.db.repository.get_rule", new_callable=AsyncMock) as mock:
        mock.return_value = None
        resp = await client.post("/api/rules/99/apply")

    assert resp.status_code == 404
    assert "Rule not found" in resp.json()["detail"]


async def test_apply_saved_rule_forwards_rule_to_helper(client):
    """The saved rule ORM object is passed directly to _apply_to_transactions."""
    rule = _make_rule(42)
    with (
        patch("finlytics.db.repository.get_rule", new_callable=AsyncMock) as get_mock,
        patch("finlytics.api.rules._apply_to_transactions", new_callable=AsyncMock) as apply_mock,
    ):
        get_mock.return_value = rule
        apply_mock.return_value = 2
        await client.post("/api/rules/42/apply")

    apply_mock.assert_called_once()
    _, rule_arg = apply_mock.call_args[0]
    assert rule_arg is rule


# ── _RuleLike + _count_matching integration (unit-level) ──────────────────────

async def test_count_matching_uses_matcher(client):
    """_count_matching loads transactions and invokes the rule matcher."""
    from finlytics.api.rules import _RuleLike, _count_matching
    from finlytics.api.schemas import RuleIn

    # Build a minimal body and RuleLike
    body = RuleIn(
        name="test",
        description_mode="contains",
        description_value="mercadona",
        skip_ai=False,
    )
    rule_like = _RuleLike(body)

    # Mock session that returns matching transactions
    mock_session = MagicMock()
    tx_match = MagicMock()
    tx_match.description = "COMPRA EN MERCADONA"
    tx_match.detail = None
    tx_match.amount = Decimal("-45.30")
    tx_match.currency = "EUR"
    tx_match.account = MagicMock()
    tx_match.account.name = "BBVA"

    tx_no_match = MagicMock()
    tx_no_match.description = "NOMINA EMPRESA"
    tx_no_match.detail = None
    tx_no_match.amount = Decimal("2850.00")
    tx_no_match.currency = "EUR"
    tx_no_match.account = MagicMock()
    tx_no_match.account.name = "BBVA"

    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = [tx_match, tx_no_match]
    mock_session.execute = AsyncMock(return_value=execute_result)

    count = await _count_matching(mock_session, rule_like)
    assert count == 1


async def test_rule_like_converts_amount_bounds(client):
    """_RuleLike converts float amount_min/max to Decimal for _matches() compatibility."""
    from finlytics.api.rules import _RuleLike
    from finlytics.api.schemas import RuleIn

    body = RuleIn(
        name="test",
        description_mode="contains",
        description_value="x",
        amount_min=10.5,
        amount_max=200.0,
        skip_ai=False,
    )
    rule_like = _RuleLike(body)

    assert isinstance(rule_like.amount_min, Decimal)
    assert isinstance(rule_like.amount_max, Decimal)
    assert rule_like.amount_min == Decimal("10.5")
    assert rule_like.amount_max == Decimal("200.0")
