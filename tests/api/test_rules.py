"""Tests for /api/rules — GET, POST, PATCH, DELETE."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Fixtures ──────────────────────────────────────────────────────────────────

_NOW = datetime(2026, 7, 7, 14, 55, 0, tzinfo=timezone.utc)


def _make_rule(**overrides):
    """Return a MagicMock representing a Rule ORM object."""
    rule = MagicMock()
    rule.id = overrides.get("id", 1)
    rule.name = overrides.get("name", "Hipoteca BBVA")
    rule.priority = overrides.get("priority", 10)
    rule.enabled = overrides.get("enabled", True)
    rule.description_mode = overrides.get("description_mode", "contains")
    rule.description_value = overrides.get("description_value", "amortización")
    rule.amount_sign = overrides.get("amount_sign", "negative")
    rule.amount_min = overrides.get("amount_min", None)
    rule.amount_max = overrides.get("amount_max", None)
    rule.account_ref = overrides.get("account_ref", "BBVA")
    rule.currency = overrides.get("currency", "EUR")
    rule.detail_mode = overrides.get("detail_mode", None)
    rule.detail_value = overrides.get("detail_value", None)
    rule.set_category = overrides.get("set_category", "Housing")
    rule.set_merchant = overrides.get("set_merchant", None)
    rule.add_tags = overrides.get("add_tags", ["hipoteca"])
    rule.skip_ai = overrides.get("skip_ai", True)
    rule.created_at = overrides.get("created_at", _NOW)
    rule.updated_at = overrides.get("updated_at", _NOW)
    return rule


_RULE_DICT = {
    "id": 1,
    "name": "Hipoteca BBVA",
    "priority": 10,
    "enabled": True,
    "description_mode": "contains",
    "description_value": "amortización",
    "amount_sign": "negative",
    "amount_min": None,
    "amount_max": None,
    "account_ref": "BBVA",
    "currency": "EUR",
    "detail_mode": None,
    "detail_value": None,
    "set_category": "Housing",
    "set_merchant": None,
    "add_tags": ["hipoteca"],
    "skip_ai": True,
    "created_at": _NOW.isoformat(),
    "updated_at": _NOW.isoformat(),
}


# ── GET /api/rules ────────────────────────────────────────────────────────────

async def test_list_rules_returns_list(client):
    with patch("finlytics.db.repository.list_rules", new_callable=AsyncMock) as mock:
        mock.return_value = [_make_rule()]
        resp = await client.get("/api/rules")

    assert resp.status_code == 200
    assert len(resp.json()) == 1


async def test_list_rules_empty(client):
    with patch("finlytics.db.repository.list_rules", new_callable=AsyncMock) as mock:
        mock.return_value = []
        resp = await client.get("/api/rules")

    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_rules_schema_fields(client):
    """Response items expose all RuleOut fields."""
    with patch("finlytics.db.repository.list_rules", new_callable=AsyncMock) as mock:
        mock.return_value = [_make_rule()]
        resp = await client.get("/api/rules")

    item = resp.json()[0]
    expected_keys = {
        "id", "name", "priority", "enabled",
        "description_mode", "description_value",
        "amount_sign", "amount_min", "amount_max",
        "account_ref", "currency",
        "detail_mode", "detail_value",
        "set_category", "set_merchant", "add_tags",
        "skip_ai", "created_at", "updated_at",
    }
    assert set(item.keys()) == expected_keys


async def test_list_rules_multiple_ordered(client):
    """Multiple rules are returned (ordering is the repository's responsibility)."""
    rules = [_make_rule(id=1, priority=10), _make_rule(id=2, priority=100, name="Nómina")]
    with patch("finlytics.db.repository.list_rules", new_callable=AsyncMock) as mock:
        mock.return_value = rules
        resp = await client.get("/api/rules")

    assert resp.status_code == 200
    assert len(resp.json()) == 2
    assert resp.json()[0]["priority"] == 10
    assert resp.json()[1]["priority"] == 100


# ── POST /api/rules ───────────────────────────────────────────────────────────

_VALID_BODY = {
    "name": "Hipoteca BBVA",
    "priority": 10,
    "enabled": True,
    "description_mode": "contains",
    "description_value": "amortización",
    "amount_sign": "negative",
    "account_ref": "BBVA",
    "currency": "EUR",
    "set_category": "Housing",
    "set_merchant": None,
    "add_tags": ["hipoteca"],
    "skip_ai": True,
}


async def test_create_rule_returns_201(client):
    with patch("finlytics.db.repository.create_rule", new_callable=AsyncMock) as mock:
        mock.return_value = _make_rule()
        resp = await client.post("/api/rules", json=_VALID_BODY)

    assert resp.status_code == 201
    assert resp.json()["id"] == 1
    assert resp.json()["name"] == "Hipoteca BBVA"


async def test_create_rule_minimal_body(client):
    """Omitting optional fields should succeed (defaults applied by schema)."""
    minimal = {
        "name": "Nómina",
        "description_mode": "contains",
        "description_value": "nomina",
        "set_category": "Income",
        "skip_ai": False,
    }
    created = _make_rule(
        name="Nómina",
        description_mode="contains",
        description_value="nomina",
        set_category="Income",
        skip_ai=False,
        priority=100,
        enabled=True,
        amount_sign=None,
        account_ref=None,
        currency=None,
        set_merchant=None,
        add_tags=[],
    )
    with patch("finlytics.db.repository.create_rule", new_callable=AsyncMock) as mock:
        mock.return_value = created
        resp = await client.post("/api/rules", json=minimal)

    assert resp.status_code == 201
    assert resp.json()["skip_ai"] is False


async def test_create_rule_422_skip_ai_without_category(client):
    """skip_ai=True requires set_category to be non-null."""
    body = {**_VALID_BODY, "skip_ai": True, "set_category": None}
    resp = await client.post("/api/rules", json=body)

    assert resp.status_code == 422
    assert "set_category" in resp.json()["detail"]


async def test_create_rule_422_invalid_regex(client):
    """description_mode=regex with an invalid pattern returns 422."""
    body = {
        **_VALID_BODY,
        "description_mode": "regex",
        "description_value": "[unclosed",
        "skip_ai": False,
    }
    resp = await client.post("/api/rules", json=body)

    assert resp.status_code == 422
    assert "regular expression" in resp.json()["detail"]


async def test_create_rule_valid_regex_accepted(client):
    """A valid regex pattern passes validation."""
    body = {
        **_VALID_BODY,
        "description_mode": "regex",
        "description_value": r"amortizaci[oó]n",
        "skip_ai": False,
    }
    created = _make_rule(description_mode="regex", description_value=r"amortizaci[oó]n", skip_ai=False)
    with patch("finlytics.db.repository.create_rule", new_callable=AsyncMock) as mock:
        mock.return_value = created
        resp = await client.post("/api/rules", json=body)

    assert resp.status_code == 201


async def test_create_rule_add_tags_list(client):
    """add_tags is returned as a list of strings."""
    rule = _make_rule(add_tags=["hipoteca", "fijo"])
    with patch("finlytics.db.repository.create_rule", new_callable=AsyncMock) as mock:
        mock.return_value = rule
        resp = await client.post("/api/rules", json=_VALID_BODY)

    assert isinstance(resp.json()["add_tags"], list)


# ── PATCH /api/rules/{id} ─────────────────────────────────────────────────────

async def test_update_rule_returns_200(client, mock_session):
    """PATCH returns 200 with the updated rule."""
    existing = _make_rule(name="Old Name")
    mock_session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=existing))
    )

    with patch("finlytics.db.repository.get_rule", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = existing
        resp = await client.patch("/api/rules/1", json={"name": "New Name"})

    assert resp.status_code == 200


async def test_update_rule_404(client, mock_session):
    """PATCH returns 404 when rule does not exist."""
    with patch("finlytics.db.repository.get_rule", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = None
        resp = await client.patch("/api/rules/999", json={"name": "X"})

    assert resp.status_code == 404
    assert "Rule not found" in resp.json()["detail"]


async def test_update_rule_422_skip_ai_without_category(client):
    """PATCH raises 422 if the resulting state has skip_ai=True and set_category=None."""
    existing = _make_rule(skip_ai=False, set_category=None)
    with patch("finlytics.db.repository.get_rule", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = existing
        resp = await client.patch("/api/rules/1", json={"skip_ai": True})

    assert resp.status_code == 422
    assert "set_category" in resp.json()["detail"]


async def test_update_rule_422_invalid_regex(client):
    """PATCH raises 422 if the effective description_value is an invalid regex."""
    existing = _make_rule(description_mode="contains", description_value="foo")
    with patch("finlytics.db.repository.get_rule", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = existing
        resp = await client.patch(
            "/api/rules/1",
            json={"description_mode": "regex", "description_value": "[bad"},
        )

    assert resp.status_code == 422
    assert "regular expression" in resp.json()["detail"]


# ── DELETE /api/rules/{id} ────────────────────────────────────────────────────

async def test_delete_rule_returns_204(client):
    with patch("finlytics.db.repository.delete_rule", new_callable=AsyncMock) as mock:
        mock.return_value = True
        resp = await client.delete("/api/rules/1")

    assert resp.status_code == 204


async def test_delete_rule_404(client):
    with patch("finlytics.db.repository.delete_rule", new_callable=AsyncMock) as mock:
        mock.return_value = False
        resp = await client.delete("/api/rules/999")

    assert resp.status_code == 404
    assert "Rule not found" in resp.json()["detail"]


async def test_delete_rule_no_body(client):
    """204 response must have no body."""
    with patch("finlytics.db.repository.delete_rule", new_callable=AsyncMock) as mock:
        mock.return_value = True
        resp = await client.delete("/api/rules/1")

    assert resp.status_code == 204
    assert resp.content == b""


# ── Rule model: add_tags default ──────────────────────────────────────────────

def test_rule_add_tags_server_default_renders_valid_json():
    """add_tags column server_default must be sa.text(\"'[]'\") to produce valid Postgres DDL.

    Guards against the regression where server_default=\"'[]'\" (plain string) caused
    SQLAlchemy to quote it into '''[]''' — invalid JSON syntax that crashed asyncpg.
    """
    from sqlalchemy import text
    from finlytics.db.models import Rule

    col = Rule.__table__.c.add_tags
    assert col.server_default is not None, "add_tags must have a server_default"
    arg = col.server_default.arg
    assert hasattr(arg, "text"), "server_default must be sa.text(...), not a bare string"
    assert arg.text == "'[]'", (
        f"server_default text must be \"'[]'\" (valid JSON), got {arg.text!r}"
    )
