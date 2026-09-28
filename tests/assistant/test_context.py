"""build_context reads the shape of the ledger through the query layer."""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

from finlytics.assistant import context as ctx_module


async def test_context_is_read_through_the_query_layer():
    session = MagicMock()
    has_investments = AsyncMock(return_value=True)
    with (
        patch.object(
            ctx_module.queries,
            "get_accounts",
            AsyncMock(return_value=[{"id": 1, "name": "BBVA", "currency": "EUR"}]),
        ),
        patch.object(
            ctx_module.queries,
            "get_categories",
            AsyncMock(return_value=[{"id": 7, "name": "Groceries"}]),
        ),
        patch.object(ctx_module.queries, "get_tags", AsyncMock(return_value=[{"name": "luz"}])),
        patch.object(
            ctx_module.queries,
            "get_transaction_date_range",
            AsyncMock(return_value={"first": date(2024, 3, 5), "last": date(2026, 7, 30)}),
        ),
        patch.object(ctx_module.queries, "has_investment_connections", has_investments),
    ):
        result = await ctx_module.build_context(session, user_id=5, today=date(2026, 7, 31))

    has_investments.assert_awaited_once_with(session, 5)
    assert result.first_transaction == date(2024, 3, 5)
    assert result.last_transaction == date(2026, 7, 30)
    assert result.has_investments is True

    rendered = ctx_module.render_context(result)
    assert "2024-03-05 → 2026-07-30" in rendered
    assert "NO investment connections" not in rendered
