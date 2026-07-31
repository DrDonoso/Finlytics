"""Tests for the assistant's read-only tool registry.

Two things matter here and neither is the SQL: that the schemas the model sees
are well-formed, and that a tool never lets a failure or an oversized result
escape into the conversation.
"""

from __future__ import annotations

import json
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from finlytics.assistant import tools


@pytest.fixture
def ctx() -> tools.ToolContext:
    return tools.ToolContext(
        session=MagicMock(),
        user_id=1,
        today=date(2026, 7, 31),
        max_rows=3,
    )


class TestSchemas:
    def test_every_tool_is_exposed(self):
        names = {s["function"]["name"] for s in tools.openai_tool_schemas()}
        assert names == set(tools.TOOLS)

    def test_schemas_are_json_serialisable(self):
        # The catalogue goes on the wire on every single turn; a non-serialisable
        # default would break every message, not just the tool that owns it.
        json.dumps(tools.openai_tool_schemas())

    @pytest.mark.parametrize("schema", tools.openai_tool_schemas())
    def test_schema_shape(self, schema):
        assert schema["type"] == "function"
        function = schema["function"]
        assert function["name"] and function["description"]
        params = function["parameters"]
        assert params["type"] == "object"
        assert isinstance(params["properties"], dict)
        # Anything listed as required must actually be declared.
        assert set(params["required"]) <= set(params["properties"])

    def test_every_tool_has_a_ui_label(self):
        # The label is what the panel shows while a query runs; without one the
        # user watches an unexplained spinner.
        assert all(t.label for t in tools.TOOLS.values())


class TestArgumentCoercion:
    def test_iso_date_is_parsed(self):
        assert tools._parse_date("2026-03-15", "from_date") == date(2026, 3, 15)

    def test_bare_month_is_read_as_first_of_month(self):
        # Models emit "2026-03" constantly; rejecting it would waste a retry.
        assert tools._parse_date("2026-03", "from_date") == date(2026, 3, 1)

    def test_blank_is_none(self):
        assert tools._parse_date("", "from_date") is None
        assert tools._parse_date(None, "from_date") is None

    def test_garbage_date_raises_tool_error(self):
        with pytest.raises(tools.ToolError, match="YYYY-MM-DD"):
            tools._parse_date("last tuesday", "from_date")

    def test_invalid_flow_raises_tool_error(self):
        with pytest.raises(tools.ToolError, match="expense"):
            tools._opt_flow("savings")

    def test_single_tag_is_wrapped(self):
        assert tools._opt_tags("luz") == ["luz"]

    def test_blank_tags_are_dropped(self):
        assert tools._opt_tags(["", "  "]) is None


class TestExecution:
    async def test_unknown_tool_returns_error(self, ctx):
        result = await tools.execute_tool("drop_database", {}, ctx)
        assert "error" in result
        assert "drop_database" in result["error"]

    async def test_tool_error_is_returned_not_raised(self, ctx):
        # A bad argument must let the model correct itself, not end the turn.
        result = await tools.execute_tool(
            "get_spending_summary", {"from_date": "yesterday"}, ctx
        )
        assert "error" in result

    async def test_unexpected_failure_is_contained(self, ctx, caplog):
        with patch.object(
            tools.queries, "get_by_category", AsyncMock(side_effect=RuntimeError("boom"))
        ):
            result = await tools.execute_tool("get_spending_by_category", {}, ctx)

        # The model is free to quote a tool result back to the user, and a real
        # database failure's text carries SQL and connection details — so it goes
        # to the log, not into the conversation.
        assert "error" in result
        assert "boom" not in result["error"]
        assert "get_spending_by_category" in result["error"]
        assert "boom" in caplog.text

    async def test_by_category_delegates_to_the_query_layer(self, ctx):
        rows = [{"category_id": 1, "category": "Groceries", "amount": 320.5, "count": 12}]
        mock = AsyncMock(return_value=rows)
        with patch.object(tools.queries, "get_by_category", mock):
            result = await tools.execute_tool(
                "get_spending_by_category",
                {"from_date": "2026-01-01", "to_date": "2026-06-30"},
                ctx,
            )
        assert result["categories"] == rows
        assert mock.await_args.kwargs["from_date"] == date(2026, 1, 1)
        assert mock.await_args.kwargs["to_date"] == date(2026, 6, 30)

    async def test_results_are_capped_and_the_cap_is_reported(self, ctx):
        rows = [
            {"category_id": i, "category": f"C{i}", "amount": float(i), "count": 1}
            for i in range(10)
        ]
        with patch.object(tools.queries, "get_by_category", AsyncMock(return_value=rows)):
            result = await tools.execute_tool("get_spending_by_category", {}, ctx)
        # Silently shortening the list would let the model state a total that
        # is missing rows it never saw, so the flag matters as much as the cap.
        assert len(result["categories"]) == ctx.max_rows
        assert result["truncated"] is True
        assert result["total_categories"] == 10


class TestSearchTransactions:
    async def test_system_rows_are_excluded(self, ctx):
        items = [
            {
                "id": 1, "transaction_date": "2026-05-02", "amount": -12.0,
                "currency": "EUR", "description": "Coffee", "category": "Dining",
                "account": "BBVA", "tags": [], "merchant": "Starbucks",
                "detail": None, "is_system": False,
                "category_confidence": 0.9, "balance_after": None,
            },
            {
                "id": 2, "transaction_date": "2026-01-01", "amount": 4000.0,
                "currency": "EUR", "description": "Saldo inicial", "category": "Other",
                "account": "BBVA", "tags": [], "merchant": None,
                "detail": None, "is_system": True,
                "category_confidence": None, "balance_after": None,
            },
        ]
        with patch.object(
            tools.queries, "get_transactions", AsyncMock(return_value=(items, 2))
        ):
            result = await tools.execute_tool("search_transactions", {}, ctx)

        # Quoting an opening-balance row back as a real transaction would be wrong.
        assert [t["description"] for t in result["transactions"]] == ["Coffee"]

    async def test_limit_is_clamped_to_the_row_cap(self, ctx):
        mock = AsyncMock(return_value=([], 0))
        with patch.object(tools.queries, "get_transactions", mock):
            await tools.execute_tool("search_transactions", {"limit": 5000}, ctx)
        assert mock.await_args.kwargs["limit"] == ctx.max_rows

    async def test_slim_rows_drop_internal_fields(self, ctx):
        items = [{
            "id": 1, "transaction_date": "2026-05-02", "amount": -12.0,
            "currency": "EUR", "description": "Coffee", "category": "Dining",
            "account": "BBVA", "tags": ["cafe"], "merchant": "Starbucks",
            "detail": None, "is_system": False,
            "category_confidence": 0.9, "balance_after": 100.0,
        }]
        with patch.object(
            tools.queries, "get_transactions", AsyncMock(return_value=(items, 1))
        ):
            result = await tools.execute_tool("search_transactions", {}, ctx)

        row = result["transactions"][0]
        assert set(row) == {
            "date", "description", "merchant", "amount", "currency",
            "category", "account", "tags",
        }


class TestComparePeriods:
    async def test_missing_bounds_are_rejected(self, ctx):
        result = await tools.execute_tool(
            "compare_periods", {"period_a_from": "2026-01-01"}, ctx
        )
        assert "error" in result

    async def test_deltas_are_sorted_by_absolute_movement(self, ctx):
        period_a = [
            {"category_id": 1, "category": "Groceries", "amount": 400.0, "count": 20},
            {"category_id": 2, "category": "Dining", "amount": 100.0, "count": 5},
        ]
        period_b = [
            {"category_id": 1, "category": "Groceries", "amount": 420.0, "count": 21},
            {"category_id": 2, "category": "Dining", "amount": 300.0, "count": 15},
        ]
        with patch.object(
            tools.queries, "get_by_category", AsyncMock(side_effect=[period_a, period_b])
        ):
            result = await tools.execute_tool(
                "compare_periods",
                {
                    "period_a_from": "2026-01-01", "period_a_to": "2026-03-31",
                    "period_b_from": "2026-04-01", "period_b_to": "2026-06-30",
                },
                ctx,
            )

        assert [c["category"] for c in result["changes"]] == ["Dining", "Groceries"]
        assert result["changes"][0]["delta"] == 200.0
        assert result["changes"][0]["delta_pct"] == 200.0

    async def test_new_category_has_no_percentage(self, ctx):
        with patch.object(
            tools.queries,
            "get_by_category",
            AsyncMock(side_effect=[
                [],
                [{"category_id": 3, "category": "Travel", "amount": 900.0, "count": 2}],
            ]),
        ):
            result = await tools.execute_tool(
                "compare_periods",
                {
                    "period_a_from": "2026-01-01", "period_a_to": "2026-03-31",
                    "period_b_from": "2026-04-01", "period_b_to": "2026-06-30",
                },
                ctx,
            )

        # No baseline means no percentage — an infinity here would be nonsense.
        assert result["changes"][0]["delta_pct"] is None
        assert result["changes"][0]["delta"] == 900.0


class TestProjectInvestment:
    async def test_delegates_to_the_deterministic_engine(self, ctx):
        result = await tools.execute_tool(
            "project_investment", {"monthly_contribution": 200, "years": 10}, ctx
        )
        assert len(result["scenarios"]) == 3
        assert "disclaimer" in result

    async def test_configured_rates_reach_the_engine(self, ctx):
        ctx.projection_rates = (1.0, 4.0, 9.0)
        result = await tools.execute_tool("project_investment", {"years": 5}, ctx)
        assert [s["annual_return_pct"] for s in result["scenarios"]] == [1.0, 4.0, 9.0]

    async def test_invalid_input_becomes_a_tool_error(self, ctx):
        result = await tools.execute_tool(
            "project_investment", {"initial_amount": -50, "years": 5}, ctx
        )
        assert "error" in result
