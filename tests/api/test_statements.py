"""Tests for /api/statements/* endpoints.

Covers:
  GET  /api/statements/months        — sorted year/month/count list
  DELETE /api/statements/month       — hard-delete + returns {deleted: N}
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch


_MONTHS = [
    {"year": 2024, "month": 6, "count": 12},
    {"year": 2024, "month": 5, "count": 8},
    {"year": 2024, "month": 1, "count": 15},
    {"year": 2023, "month": 12, "count": 7},
]


# ── GET /api/statements/months ────────────────────────────────────────────────

async def test_list_months_status_200(client):
    with patch("finlytics.db.queries.get_statement_months", new_callable=AsyncMock) as mock:
        mock.return_value = _MONTHS
        resp = await client.get("/api/statements/months")

    assert resp.status_code == 200


async def test_list_months_returns_all_entries(client):
    with patch("finlytics.db.queries.get_statement_months", new_callable=AsyncMock) as mock:
        mock.return_value = _MONTHS
        resp = await client.get("/api/statements/months")

    assert len(resp.json()) == 4


async def test_list_months_schema_fields(client):
    """Each entry has exactly year (int), month (int), count (int)."""
    with patch("finlytics.db.queries.get_statement_months", new_callable=AsyncMock) as mock:
        mock.return_value = [_MONTHS[0]]
        resp = await client.get("/api/statements/months")

    item = resp.json()[0]
    assert set(item.keys()) == {"year", "month", "count"}
    assert isinstance(item["year"], int)
    assert isinstance(item["month"], int)
    assert isinstance(item["count"], int)


async def test_list_months_values_correct(client):
    with patch("finlytics.db.queries.get_statement_months", new_callable=AsyncMock) as mock:
        mock.return_value = [_MONTHS[0]]
        resp = await client.get("/api/statements/months")

    item = resp.json()[0]
    assert item["year"] == 2024
    assert item["month"] == 6
    assert item["count"] == 12


async def test_list_months_sorted_desc(client):
    """Entries are ordered DESC by (year, month) — newest first."""
    with patch("finlytics.db.queries.get_statement_months", new_callable=AsyncMock) as mock:
        mock.return_value = _MONTHS
        resp = await client.get("/api/statements/months")

    rows = resp.json()
    pairs = [(r["year"], r["month"]) for r in rows]
    assert pairs == sorted(pairs, reverse=True)


async def test_list_months_empty(client):
    with patch("finlytics.db.queries.get_statement_months", new_callable=AsyncMock) as mock:
        mock.return_value = []
        resp = await client.get("/api/statements/months")

    assert resp.status_code == 200
    assert resp.json() == []


# ── DELETE /api/statements/month ──────────────────────────────────────────────

async def test_delete_month_status_200(client):
    with patch("finlytics.db.queries.delete_statement_month", new_callable=AsyncMock) as mock:
        mock.return_value = 8
        resp = await client.delete("/api/statements/month?year=2024&month=5")

    assert resp.status_code == 200


async def test_delete_month_returns_deleted_count(client):
    with patch("finlytics.db.queries.delete_statement_month", new_callable=AsyncMock) as mock:
        mock.return_value = 8
        resp = await client.delete("/api/statements/month?year=2024&month=5")

    assert resp.json() == {"deleted": 8}


async def test_delete_month_zero_deleted(client):
    """Month with no transactions returns {deleted: 0} — not an error."""
    with patch("finlytics.db.queries.delete_statement_month", new_callable=AsyncMock) as mock:
        mock.return_value = 0
        resp = await client.delete("/api/statements/month?year=2023&month=12")

    assert resp.status_code == 200
    assert resp.json()["deleted"] == 0


async def test_delete_month_passes_year_month(client):
    """Router passes correct year and month kwargs to the query function."""
    with patch("finlytics.db.queries.delete_statement_month", new_callable=AsyncMock) as mock:
        mock.return_value = 5
        await client.delete("/api/statements/month?year=2024&month=3")

    mock.assert_called_once()
    _, kwargs = mock.call_args
    assert kwargs["year"] == 2024
    assert kwargs["month"] == 3


async def test_delete_month_different_params(client):
    """Verify year/month forwarding for a different calendar month."""
    with patch("finlytics.db.queries.delete_statement_month", new_callable=AsyncMock) as mock:
        mock.return_value = 15
        resp = await client.delete("/api/statements/month?year=2023&month=1")

    _, kwargs = mock.call_args
    assert kwargs["year"] == 2023
    assert kwargs["month"] == 1
    assert resp.json()["deleted"] == 15
