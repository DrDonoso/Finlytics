"""Tests for GET /api/summary/* endpoints."""

from datetime import date
from unittest.mock import AsyncMock, patch


_OVERVIEW = {
    "total_expense": 320.75,
    "total_income": 3200.0,
    "net": 2879.25,
    "num_transactions": 12,
    "top_category": {"name": "Groceries", "amount": 140.0},
    "currency": "EUR",
}

_BY_CATEGORY = [
    {"category_id": 1, "category": "Groceries", "amount": 140.0, "count": 5},
    {"category_id": 2, "category": "Dining", "amount": 88.5, "count": 3},
]

_BY_MONTH = [
    {"month": "2024-05", "expense": 150.0, "income": 3200.0, "net": 3050.0},
    {"month": "2024-06", "expense": 170.75, "income": 0.0, "net": -170.75},
]

_BY_ACCOUNT = [
    {"account": "BBVA", "expense": 320.75, "income": 3200.0, "net": 2879.25, "currency": "EUR"},
]


async def test_overview_schema(client):
    with patch("finlytics.db.queries.get_overview", new_callable=AsyncMock) as mock:
        mock.return_value = _OVERVIEW
        resp = await client.get("/api/summary/overview")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total_expense"] == 320.75
    assert body["total_income"] == 3200.0
    assert body["net"] == 2879.25
    assert body["num_transactions"] == 12
    assert body["top_category"]["name"] == "Groceries"
    assert body["currency"] == "EUR"


async def test_overview_null_top_category(client):
    overview_empty = {**_OVERVIEW, "top_category": None, "num_transactions": 0,
                      "total_expense": 0.0, "total_income": 0.0, "net": 0.0}
    with patch("finlytics.db.queries.get_overview", new_callable=AsyncMock) as mock:
        mock.return_value = overview_empty
        resp = await client.get("/api/summary/overview")

    assert resp.status_code == 200
    assert resp.json()["top_category"] is None


async def test_overview_passes_filters(client):
    with patch("finlytics.db.queries.get_overview", new_callable=AsyncMock) as mock:
        mock.return_value = _OVERVIEW
        resp = await client.get("/api/summary/overview?from=2024-01-01&to=2024-06-30&account_id=1")

    assert resp.status_code == 200
    _, kwargs = mock.call_args
    assert kwargs["from_date"] == date(2024, 1, 1)
    assert kwargs["to_date"] == date(2024, 6, 30)
    assert kwargs["account_id"] == 1


async def test_by_category_schema(client):
    with patch("finlytics.db.queries.get_by_category", new_callable=AsyncMock) as mock:
        mock.return_value = _BY_CATEGORY
        resp = await client.get("/api/summary/by-category")

    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 2
    assert set(rows[0].keys()) == {"category_id", "category", "amount", "count"}
    # Must be sorted desc by amount
    assert rows[0]["amount"] >= rows[1]["amount"]


async def test_by_category_empty(client):
    with patch("finlytics.db.queries.get_by_category", new_callable=AsyncMock) as mock:
        mock.return_value = []
        resp = await client.get("/api/summary/by-category")

    assert resp.status_code == 200
    assert resp.json() == []


async def test_by_month_schema(client):
    with patch("finlytics.db.queries.get_by_month", new_callable=AsyncMock) as mock:
        mock.return_value = _BY_MONTH
        resp = await client.get("/api/summary/by-month")

    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 2
    assert set(rows[0].keys()) == {"month", "expense", "income", "net"}
    assert rows[0]["month"] == "2024-05"


async def test_by_month_passes_category_id_filter(client):
    with patch("finlytics.db.queries.get_by_month", new_callable=AsyncMock) as mock:
        mock.return_value = []
        resp = await client.get("/api/summary/by-month?category_id=3")

    _, kwargs = mock.call_args
    assert kwargs["category_id"] == 3


# ── GET /api/summary/by-day ───────────────────────────────────────────────────

_BY_DAY = [
    {"day": "2024-05-10", "expense": 50.0, "income": 0.0, "net": -50.0},
    {"day": "2024-05-15", "expense": 0.0, "income": 3200.0, "net": 3200.0},
    {"day": "2024-06-03", "expense": 120.75, "income": 0.0, "net": -120.75},
]


async def test_by_day_schema(client):
    with patch("finlytics.db.queries.get_by_day", new_callable=AsyncMock) as mock:
        mock.return_value = _BY_DAY
        resp = await client.get("/api/summary/by-day")

    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 3
    assert set(rows[0].keys()) == {"day", "expense", "income", "net"}
    assert rows[0]["day"] == "2024-05-10"
    assert rows[0]["expense"] == 50.0
    assert rows[0]["net"] == -50.0


async def test_by_day_net_computed_correctly(client):
    data = [{"day": "2024-07-01", "expense": 100.0, "income": 300.0, "net": 200.0}]
    with patch("finlytics.db.queries.get_by_day", new_callable=AsyncMock) as mock:
        mock.return_value = data
        resp = await client.get("/api/summary/by-day")

    row = resp.json()[0]
    assert row["net"] == row["income"] - row["expense"]


async def test_by_day_chronological_order(client):
    with patch("finlytics.db.queries.get_by_day", new_callable=AsyncMock) as mock:
        mock.return_value = _BY_DAY
        resp = await client.get("/api/summary/by-day")

    days = [r["day"] for r in resp.json()]
    assert days == sorted(days)


async def test_by_day_passes_filters(client):
    with patch("finlytics.db.queries.get_by_day", new_callable=AsyncMock) as mock:
        mock.return_value = []
        resp = await client.get(
            "/api/summary/by-day?from=2024-01-01&to=2024-06-30&account_id=2&category_id=5"
        )

    assert resp.status_code == 200
    _, kwargs = mock.call_args
    assert kwargs["from_date"] == date(2024, 1, 1)
    assert kwargs["to_date"] == date(2024, 6, 30)
    assert kwargs["account_id"] == 2
    assert kwargs["category_id"] == 5


async def test_by_day_passes_tag_filter(client):
    with patch("finlytics.db.queries.get_by_day", new_callable=AsyncMock) as mock:
        mock.return_value = []
        resp = await client.get("/api/summary/by-day?tag=food&tag=travel")

    _, kwargs = mock.call_args
    assert kwargs["tags"] == ["food", "travel"]


async def test_by_day_passes_flow_filter(client):
    with patch("finlytics.db.queries.get_by_day", new_callable=AsyncMock) as mock:
        mock.return_value = []
        resp = await client.get("/api/summary/by-day?flow=expense")

    _, kwargs = mock.call_args
    assert kwargs["flow"] == "expense"


async def test_by_day_empty_when_no_transactions(client):
    with patch("finlytics.db.queries.get_by_day", new_callable=AsyncMock) as mock:
        mock.return_value = []
        resp = await client.get("/api/summary/by-day")

    assert resp.status_code == 200
    assert resp.json() == []


async def test_by_account_schema(client):
    with patch("finlytics.db.queries.get_by_account", new_callable=AsyncMock) as mock:
        mock.return_value = _BY_ACCOUNT
        resp = await client.get("/api/summary/by-account")

    assert resp.status_code == 200
    row = resp.json()[0]
    assert set(row.keys()) == {"account", "expense", "income", "net", "currency"}
    assert row["account"] == "BBVA"
    assert row["currency"] == "EUR"


# ── GET /api/summary/cashflow ─────────────────────────────────────────────────

_CASHFLOW = {
    "income": [
        {"category": "Salary", "amount": 3200.0},
        {"category": "Freelance", "amount": 500.0},
    ],
    "expense": [
        {"category": "Groceries", "amount": 140.0},
        {"category": "Dining", "amount": 88.5},
    ],
    "total_income": 3700.0,
    "total_expense": 228.5,
    "currency": "EUR",
}


async def test_cashflow_schema(client):
    with patch("finlytics.db.queries.get_cashflow", new_callable=AsyncMock) as mock:
        mock.return_value = _CASHFLOW
        resp = await client.get("/api/summary/cashflow")

    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"income", "expense", "total_income", "total_expense", "currency"}
    assert body["total_income"] == 3700.0
    assert body["total_expense"] == 228.5
    assert body["currency"] == "EUR"


async def test_cashflow_income_amounts_positive(client):
    with patch("finlytics.db.queries.get_cashflow", new_callable=AsyncMock) as mock:
        mock.return_value = _CASHFLOW
        resp = await client.get("/api/summary/cashflow")

    for row in resp.json()["income"]:
        assert row["amount"] > 0, f"Income amount must be positive, got {row['amount']}"


async def test_cashflow_expense_amounts_positive(client):
    """Expense entries are magnitudes (positive), even though transactions are negative."""
    with patch("finlytics.db.queries.get_cashflow", new_callable=AsyncMock) as mock:
        mock.return_value = _CASHFLOW
        resp = await client.get("/api/summary/cashflow")

    for row in resp.json()["expense"]:
        assert row["amount"] > 0, f"Expense magnitude must be positive, got {row['amount']}"


async def test_cashflow_income_sorted_desc(client):
    with patch("finlytics.db.queries.get_cashflow", new_callable=AsyncMock) as mock:
        mock.return_value = _CASHFLOW
        resp = await client.get("/api/summary/cashflow")

    amounts = [r["amount"] for r in resp.json()["income"]]
    assert amounts == sorted(amounts, reverse=True)


async def test_cashflow_expense_sorted_desc(client):
    with patch("finlytics.db.queries.get_cashflow", new_callable=AsyncMock) as mock:
        mock.return_value = _CASHFLOW
        resp = await client.get("/api/summary/cashflow")

    amounts = [r["amount"] for r in resp.json()["expense"]]
    assert amounts == sorted(amounts, reverse=True)


async def test_cashflow_passes_filters(client):
    with patch("finlytics.db.queries.get_cashflow", new_callable=AsyncMock) as mock:
        mock.return_value = _CASHFLOW
        resp = await client.get(
            "/api/summary/cashflow?from=2024-01-01&to=2024-06-30&account_id=1"
        )

    assert resp.status_code == 200
    _, kwargs = mock.call_args
    assert kwargs["from_date"] == date(2024, 1, 1)
    assert kwargs["to_date"] == date(2024, 6, 30)
    assert kwargs["account_id"] == 1


async def test_cashflow_empty(client):
    empty = {
        "income": [], "expense": [],
        "total_income": 0.0, "total_expense": 0.0, "currency": "EUR",
    }
    with patch("finlytics.db.queries.get_cashflow", new_callable=AsyncMock) as mock:
        mock.return_value = empty
        resp = await client.get("/api/summary/cashflow")

    assert resp.status_code == 200
    body = resp.json()
    assert body["income"] == []
    assert body["expense"] == []
    assert body["total_income"] == 0.0
    assert body["total_expense"] == 0.0


async def test_cashflow_category_row_schema(client):
    with patch("finlytics.db.queries.get_cashflow", new_callable=AsyncMock) as mock:
        mock.return_value = _CASHFLOW
        resp = await client.get("/api/summary/cashflow")

    row = resp.json()["income"][0]
    assert set(row.keys()) == {"category", "amount"}
    assert isinstance(row["category"], str)
    assert isinstance(row["amount"], float)


# ── Tag filter on summary endpoints ──────────────────────────────────────────

async def test_overview_tag_filter_passed(client):
    with patch("finlytics.db.queries.get_overview", new_callable=AsyncMock) as mock:
        mock.return_value = _OVERVIEW
        resp = await client.get("/api/summary/overview?tag=luz")

    assert resp.status_code == 200
    _, kwargs = mock.call_args
    assert kwargs["tags"] == ["luz"]


async def test_by_category_tag_filter_passed(client):
    with patch("finlytics.db.queries.get_by_category", new_callable=AsyncMock) as mock:
        mock.return_value = []
        resp = await client.get("/api/summary/by-category?tag=agua")

    assert resp.status_code == 200
    _, kwargs = mock.call_args
    assert kwargs["tags"] == ["agua"]


async def test_by_month_tag_filter_passed(client):
    with patch("finlytics.db.queries.get_by_month", new_callable=AsyncMock) as mock:
        mock.return_value = []
        resp = await client.get("/api/summary/by-month?tag=gas")

    assert resp.status_code == 200
    _, kwargs = mock.call_args
    assert kwargs["tags"] == ["gas"]


async def test_by_account_tag_filter_passed(client):
    with patch("finlytics.db.queries.get_by_account", new_callable=AsyncMock) as mock:
        mock.return_value = []
        resp = await client.get("/api/summary/by-account?tag=internet")

    assert resp.status_code == 200
    _, kwargs = mock.call_args
    assert kwargs["tags"] == ["internet"]


async def test_cashflow_tag_filter_passed(client):
    with patch("finlytics.db.queries.get_cashflow", new_callable=AsyncMock) as mock:
        mock.return_value = _CASHFLOW
        resp = await client.get("/api/summary/cashflow?tag=luz")

    assert resp.status_code == 200
    _, kwargs = mock.call_args
    assert kwargs["tags"] == ["luz"]


async def test_cashflow_tag_none_when_not_provided(client):
    """When ?tag is absent, None is forwarded (no filter applied)."""
    with patch("finlytics.db.queries.get_cashflow", new_callable=AsyncMock) as mock:
        mock.return_value = _CASHFLOW
        await client.get("/api/summary/cashflow")

    _, kwargs = mock.call_args
    assert kwargs["tags"] is None


async def test_cashflow_multi_tag_or_filter(client):
    """?tag=luz&tag=agua passes both to get_cashflow as a list (OR semantics)."""
    with patch("finlytics.db.queries.get_cashflow", new_callable=AsyncMock) as mock:
        mock.return_value = _CASHFLOW
        resp = await client.get("/api/summary/cashflow?tag=luz&tag=agua")

    assert resp.status_code == 200
    _, kwargs = mock.call_args
    assert set(kwargs["tags"]) == {"luz", "agua"}


# ── GET /api/summary/months ───────────────────────────────────────────────────

_STATEMENT_MONTHS_RAW = [
    {"year": 2024, "month": 6, "count": 12},
    {"year": 2024, "month": 5, "count": 8},
    {"year": 2024, "month": 1, "count": 15},
    {"year": 2023, "month": 12, "count": 7},
]


async def test_transaction_months_status_200(client):
    with patch("finlytics.db.queries.get_statement_months", new_callable=AsyncMock) as mock:
        mock.return_value = _STATEMENT_MONTHS_RAW
        resp = await client.get("/api/summary/months")

    assert resp.status_code == 200


async def test_transaction_months_schema(client):
    """Response has exactly {months: [...], latest: str}."""
    with patch("finlytics.db.queries.get_statement_months", new_callable=AsyncMock) as mock:
        mock.return_value = _STATEMENT_MONTHS_RAW
        resp = await client.get("/api/summary/months")

    body = resp.json()
    assert set(body.keys()) == {"months", "latest"}
    assert isinstance(body["months"], list)
    assert isinstance(body["latest"], str)


async def test_transaction_months_format_yyyy_mm(client):
    """Each entry in months is a zero-padded YYYY-MM string."""
    with patch("finlytics.db.queries.get_statement_months", new_callable=AsyncMock) as mock:
        mock.return_value = _STATEMENT_MONTHS_RAW
        resp = await client.get("/api/summary/months")

    for m in resp.json()["months"]:
        assert len(m) == 7, f"Expected YYYY-MM (7 chars), got '{m}'"
        assert m[4] == "-"


async def test_transaction_months_sorted_asc(client):
    """Months are sorted ascending so the frontend can take the last as default."""
    with patch("finlytics.db.queries.get_statement_months", new_callable=AsyncMock) as mock:
        mock.return_value = _STATEMENT_MONTHS_RAW
        resp = await client.get("/api/summary/months")

    months = resp.json()["months"]
    assert months == sorted(months)


async def test_transaction_months_latest_is_last(client):
    """latest equals the last element of months."""
    with patch("finlytics.db.queries.get_statement_months", new_callable=AsyncMock) as mock:
        mock.return_value = _STATEMENT_MONTHS_RAW
        resp = await client.get("/api/summary/months")

    body = resp.json()
    assert body["latest"] == body["months"][-1]
    assert body["latest"] == "2024-06"


async def test_transaction_months_values_correct(client):
    with patch("finlytics.db.queries.get_statement_months", new_callable=AsyncMock) as mock:
        mock.return_value = _STATEMENT_MONTHS_RAW
        resp = await client.get("/api/summary/months")

    assert resp.json()["months"] == ["2023-12", "2024-01", "2024-05", "2024-06"]


async def test_transaction_months_empty(client):
    """No transactions → months=[], latest=null, still 200."""
    with patch("finlytics.db.queries.get_statement_months", new_callable=AsyncMock) as mock:
        mock.return_value = []
        resp = await client.get("/api/summary/months")

    assert resp.status_code == 200
    body = resp.json()
    assert body["months"] == []
    assert body["latest"] is None


async def test_transaction_months_calls_get_statement_months(client):
    """Endpoint delegates to get_statement_months (reuses existing query)."""
    with patch("finlytics.db.queries.get_statement_months", new_callable=AsyncMock) as mock:
        mock.return_value = []
        await client.get("/api/summary/months")

    mock.assert_called_once()


async def test_transaction_months_single_entry(client):
    with patch("finlytics.db.queries.get_statement_months", new_callable=AsyncMock) as mock:
        mock.return_value = [{"year": 2025, "month": 3, "count": 5}]
        resp = await client.get("/api/summary/months")

    body = resp.json()
    assert body["months"] == ["2025-03"]
    assert body["latest"] == "2025-03"


async def test_transactions_multi_tag_no_duplicate_rows(client):
    """Multi-tag OR filter: the query layer gets a list; no row duplication from the API layer."""
    tx_base = {
        "id": 1, "transaction_date": "2024-06-01", "amount": -50.0,
        "currency": "EUR", "description": "LUZ", "category": "Utilities",
        "account": "BBVA", "category_confidence": 0.9, "balance_after": None,
        "tags": ["luz", "agua"],
    }
    tx2 = {**tx_base, "id": 2, "tags": ["luz"]}
    with patch("finlytics.db.queries.get_transactions", new_callable=AsyncMock) as mock:
        mock.return_value = ([tx_base, tx2], 2)
        resp = await client.get("/api/transactions?tag=luz&tag=agua")

    body = resp.json()
    assert body["total"] == 2
    ids = [item["id"] for item in body["items"]]
    assert len(ids) == len(set(ids)), "Duplicate transaction IDs — row multiplication!"


# ── category_id cross-filter ──────────────────────────────────────────────────

async def test_overview_passes_category_id_filter(client):
    with patch("finlytics.db.queries.get_overview", new_callable=AsyncMock) as mock:
        mock.return_value = _OVERVIEW
        resp = await client.get("/api/summary/overview?category_id=5")

    assert resp.status_code == 200
    _, kwargs = mock.call_args
    assert kwargs["category_id"] == 5


async def test_by_account_passes_category_id_filter(client):
    with patch("finlytics.db.queries.get_by_account", new_callable=AsyncMock) as mock:
        mock.return_value = _BY_ACCOUNT
        resp = await client.get("/api/summary/by-account?category_id=5")

    assert resp.status_code == 200
    _, kwargs = mock.call_args
    assert kwargs["category_id"] == 5


async def test_cashflow_passes_category_id_filter(client):
    with patch("finlytics.db.queries.get_cashflow", new_callable=AsyncMock) as mock:
        mock.return_value = _CASHFLOW
        resp = await client.get("/api/summary/cashflow?category_id=5")

    assert resp.status_code == 200
    _, kwargs = mock.call_args
    assert kwargs["category_id"] == 5


async def test_by_category_includes_category_id(client):
    with patch("finlytics.db.queries.get_by_category", new_callable=AsyncMock) as mock:
        mock.return_value = _BY_CATEGORY
        resp = await client.get("/api/summary/by-category")

    rows = resp.json()
    assert rows[0]["category_id"] == 1
    assert rows[1]["category_id"] == 2


async def test_overview_category_id_and_tag_compose(client):
    """category_id and tag can both be set — both are forwarded to the query layer."""
    with patch("finlytics.db.queries.get_overview", new_callable=AsyncMock) as mock:
        mock.return_value = _OVERVIEW
        resp = await client.get("/api/summary/overview?category_id=5&tag=luz")

    assert resp.status_code == 200
    _, kwargs = mock.call_args
    assert kwargs["category_id"] == 5
    assert kwargs["tags"] == ["luz"]


async def test_cashflow_category_id_and_tag_compose(client):
    """category_id and tag can both be set — both are forwarded to the query layer."""
    with patch("finlytics.db.queries.get_cashflow", new_callable=AsyncMock) as mock:
        mock.return_value = _CASHFLOW
        resp = await client.get("/api/summary/cashflow?category_id=5&tag=luz")

    assert resp.status_code == 200
    _, kwargs = mock.call_args
    assert kwargs["category_id"] == 5
    assert kwargs["tags"] == ["luz"]


# ── Flow filter ───────────────────────────────────────────────────────────────

async def test_overview_flow_expense_filter(client):
    """?flow=expense is forwarded to get_overview as flow='expense'."""
    with patch("finlytics.db.queries.get_overview", new_callable=AsyncMock) as mock:
        mock.return_value = _OVERVIEW
        resp = await client.get("/api/summary/overview?flow=expense")

    assert resp.status_code == 200
    _, kwargs = mock.call_args
    assert kwargs["flow"] == "expense"


async def test_overview_flow_income_filter(client):
    """?flow=income is forwarded to get_overview as flow='income'."""
    with patch("finlytics.db.queries.get_overview", new_callable=AsyncMock) as mock:
        mock.return_value = _OVERVIEW
        resp = await client.get("/api/summary/overview?flow=income")

    assert resp.status_code == 200
    _, kwargs = mock.call_args
    assert kwargs["flow"] == "income"


async def test_overview_flow_none_when_not_provided(client):
    """When ?flow is absent, None is forwarded (no filter)."""
    with patch("finlytics.db.queries.get_overview", new_callable=AsyncMock) as mock:
        mock.return_value = _OVERVIEW
        await client.get("/api/summary/overview")

    _, kwargs = mock.call_args
    assert kwargs["flow"] is None


async def test_overview_flow_invalid_returns_422(client):
    """An unknown flow value returns 422."""
    resp = await client.get("/api/summary/overview?flow=transfer")
    assert resp.status_code == 422


async def test_overview_flow_composes_with_account_id(client):
    """flow and account_id can both be set — both are forwarded to the query layer."""
    with patch("finlytics.db.queries.get_overview", new_callable=AsyncMock) as mock:
        mock.return_value = _OVERVIEW
        resp = await client.get("/api/summary/overview?account_id=1&flow=expense")

    assert resp.status_code == 200
    _, kwargs = mock.call_args
    assert kwargs["account_id"] == 1
    assert kwargs["flow"] == "expense"


# ── Description / amount filters on overview ─────────────────────────────────

async def test_overview_description_filter_forwarded(client):
    """?description=mercadona is forwarded to get_overview."""
    with patch("finlytics.db.queries.get_overview", new_callable=AsyncMock) as mock:
        mock.return_value = _OVERVIEW
        resp = await client.get("/api/summary/overview?description=mercadona")

    assert resp.status_code == 200
    _, kwargs = mock.call_args
    assert kwargs["description"] == "mercadona"


async def test_overview_description_none_when_not_provided(client):
    """When ?description is absent, None is forwarded (no filter)."""
    with patch("finlytics.db.queries.get_overview", new_callable=AsyncMock) as mock:
        mock.return_value = _OVERVIEW
        await client.get("/api/summary/overview")

    _, kwargs = mock.call_args
    assert kwargs["description"] is None


async def test_overview_amount_min_forwarded(client):
    """?amount_min=10 is forwarded to get_overview."""
    with patch("finlytics.db.queries.get_overview", new_callable=AsyncMock) as mock:
        mock.return_value = _OVERVIEW
        resp = await client.get("/api/summary/overview?amount_min=10")

    assert resp.status_code == 200
    _, kwargs = mock.call_args
    assert kwargs["amount_min"] == 10.0


async def test_overview_amount_max_forwarded(client):
    """?amount_max=500 is forwarded to get_overview."""
    with patch("finlytics.db.queries.get_overview", new_callable=AsyncMock) as mock:
        mock.return_value = _OVERVIEW
        resp = await client.get("/api/summary/overview?amount_max=500")

    assert resp.status_code == 200
    _, kwargs = mock.call_args
    assert kwargs["amount_max"] == 500.0


async def test_overview_amount_min_none_when_not_provided(client):
    """When ?amount_min is absent, None is forwarded."""
    with patch("finlytics.db.queries.get_overview", new_callable=AsyncMock) as mock:
        mock.return_value = _OVERVIEW
        await client.get("/api/summary/overview")

    _, kwargs = mock.call_args
    assert kwargs["amount_min"] is None


async def test_overview_amount_max_none_when_not_provided(client):
    """When ?amount_max is absent, None is forwarded."""
    with patch("finlytics.db.queries.get_overview", new_callable=AsyncMock) as mock:
        mock.return_value = _OVERVIEW
        await client.get("/api/summary/overview")

    _, kwargs = mock.call_args
    assert kwargs["amount_max"] is None


async def test_overview_amount_min_negative_returns_422(client):
    """A negative amount_min returns 422."""
    resp = await client.get("/api/summary/overview?amount_min=-1")
    assert resp.status_code == 422


async def test_overview_amount_max_negative_returns_422(client):
    """A negative amount_max returns 422."""
    resp = await client.get("/api/summary/overview?amount_max=-1")
    assert resp.status_code == 422


async def test_overview_description_amount_range_compose(client):
    """description, amount_min, and amount_max can all be combined; totals change accordingly."""
    filtered_overview = {
        **_OVERVIEW,
        "total_expense": 42.5,
        "total_income": 0.0,
        "net": -42.5,
        "num_transactions": 1,
        "top_category": {"name": "Groceries", "amount": 42.5},
    }
    with patch("finlytics.db.queries.get_overview", new_callable=AsyncMock) as mock:
        mock.return_value = filtered_overview
        resp = await client.get(
            "/api/summary/overview?description=MERCADONA&amount_min=10&amount_max=100"
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["total_expense"] == 42.5
    assert body["num_transactions"] == 1
    _, kwargs = mock.call_args
    assert kwargs["description"] == "MERCADONA"
    assert kwargs["amount_min"] == 10.0
    assert kwargs["amount_max"] == 100.0


async def test_by_month_flow_expense_filter(client):
    """?flow=expense is forwarded to get_by_month as flow='expense'."""
    with patch("finlytics.db.queries.get_by_month", new_callable=AsyncMock) as mock:
        mock.return_value = []
        resp = await client.get("/api/summary/by-month?flow=expense")

    assert resp.status_code == 200
    _, kwargs = mock.call_args
    assert kwargs["flow"] == "expense"


async def test_by_month_flow_income_filter(client):
    """?flow=income is forwarded to get_by_month as flow='income'."""
    with patch("finlytics.db.queries.get_by_month", new_callable=AsyncMock) as mock:
        mock.return_value = []
        resp = await client.get("/api/summary/by-month?flow=income")

    assert resp.status_code == 200
    _, kwargs = mock.call_args
    assert kwargs["flow"] == "income"


async def test_cashflow_flow_expense_filter(client):
    """?flow=expense is forwarded to get_cashflow as flow='expense'."""
    with patch("finlytics.db.queries.get_cashflow", new_callable=AsyncMock) as mock:
        mock.return_value = _CASHFLOW
        resp = await client.get("/api/summary/cashflow?flow=expense")

    assert resp.status_code == 200
    _, kwargs = mock.call_args
    assert kwargs["flow"] == "expense"


async def test_cashflow_flow_income_filter(client):
    """?flow=income is forwarded to get_cashflow as flow='income'."""
    with patch("finlytics.db.queries.get_cashflow", new_callable=AsyncMock) as mock:
        mock.return_value = _CASHFLOW
        resp = await client.get("/api/summary/cashflow?flow=income")

    assert resp.status_code == 200
    _, kwargs = mock.call_args
    assert kwargs["flow"] == "income"


async def test_cashflow_flow_invalid_returns_422(client):
    """An unknown flow value on cashflow returns 422."""
    resp = await client.get("/api/summary/cashflow?flow=transfer")
    assert resp.status_code == 422


async def test_by_category_flow_filter_passed(client):
    """?flow=expense is forwarded to get_by_category."""
    with patch("finlytics.db.queries.get_by_category", new_callable=AsyncMock) as mock:
        mock.return_value = []
        resp = await client.get("/api/summary/by-category?flow=expense")

    assert resp.status_code == 200
    _, kwargs = mock.call_args
    assert kwargs["flow"] == "expense"


async def test_by_account_flow_filter_passed(client):
    """?flow=income is forwarded to get_by_account."""
    with patch("finlytics.db.queries.get_by_account", new_callable=AsyncMock) as mock:
        mock.return_value = []
        resp = await client.get("/api/summary/by-account?flow=income")

    assert resp.status_code == 200
    _, kwargs = mock.call_args
    assert kwargs["flow"] == "income"


# ── Merchant filter on overview ───────────────────────────────────────────────

async def test_overview_merchant_filter_forwarded(client):
    """?merchant=amazon is forwarded to get_overview."""
    with patch("finlytics.db.queries.get_overview", new_callable=AsyncMock) as mock:
        mock.return_value = _OVERVIEW
        resp = await client.get("/api/summary/overview?merchant=amazon")

    assert resp.status_code == 200
    _, kwargs = mock.call_args
    assert kwargs["merchant"] == "amazon"


async def test_overview_merchant_none_when_not_provided(client):
    """When ?merchant is absent, None is forwarded (no filter)."""
    with patch("finlytics.db.queries.get_overview", new_callable=AsyncMock) as mock:
        mock.return_value = _OVERVIEW
        await client.get("/api/summary/overview")

    _, kwargs = mock.call_args
    assert kwargs["merchant"] is None


# ── Merchant filter: totals + composability + wildcard ────────────────────────

async def test_overview_merchant_filter_totals_reflect_filter(client):
    """When ?merchant= is set, the overview totals reflect only the matching transactions."""
    filtered = {
        **_OVERVIEW,
        "total_expense": 42.5,
        "total_income": 0.0,
        "net": -42.5,
        "num_transactions": 1,
        "top_category": {"name": "Groceries", "amount": 42.5},
    }
    with patch("finlytics.db.queries.get_overview", new_callable=AsyncMock) as mock:
        mock.return_value = filtered
        resp = await client.get("/api/summary/overview?merchant=Mercadona")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total_expense"] == 42.5
    assert body["num_transactions"] == 1
    _, kwargs = mock.call_args
    assert kwargs["merchant"] == "Mercadona"


async def test_overview_merchant_composes_with_description(client):
    """?merchant= and ?description= can both be set — both are forwarded to get_overview."""
    with patch("finlytics.db.queries.get_overview", new_callable=AsyncMock) as mock:
        mock.return_value = _OVERVIEW
        resp = await client.get("/api/summary/overview?merchant=Amazon&description=PRIME")

    assert resp.status_code == 200
    _, kwargs = mock.call_args
    assert kwargs["merchant"] == "Amazon"
    assert kwargs["description"] == "PRIME"


async def test_overview_merchant_percent_treated_literally(client):
    """A '%' in the merchant filter for overview is forwarded as a literal to get_overview."""
    with patch("finlytics.db.queries.get_overview", new_callable=AsyncMock) as mock:
        mock.return_value = _OVERVIEW
        resp = await client.get("/api/summary/overview?merchant=100%25")

    assert resp.status_code == 200
    _, kwargs = mock.call_args
    # FastAPI URL-decodes %25 → '%'; the literal value must reach the query layer.
    assert kwargs["merchant"] == "100%"


# ── GET /api/summary/by-merchant ─────────────────────────────────────────────

_BY_MERCHANT = [
    {"merchant": "Mercadona", "amount": 240.0, "count": 8},
    {"merchant": "Netflix",   "amount": 14.99, "count": 1},
]


async def test_by_merchant_schema(client):
    with patch("finlytics.db.queries.get_by_merchant", new_callable=AsyncMock) as mock:
        mock.return_value = _BY_MERCHANT
        resp = await client.get("/api/summary/by-merchant")

    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 2
    assert set(rows[0].keys()) == {"merchant", "amount", "count"}
    assert rows[0]["merchant"] == "Mercadona"
    assert rows[0]["amount"] == 240.0
    assert rows[0]["count"] == 8


async def test_by_merchant_expense_magnitude_positive(client):
    """Amounts are positive magnitudes (expense direction)."""
    with patch("finlytics.db.queries.get_by_merchant", new_callable=AsyncMock) as mock:
        mock.return_value = _BY_MERCHANT
        resp = await client.get("/api/summary/by-merchant")

    for row in resp.json():
        assert row["amount"] > 0, f"Expected positive magnitude, got {row['amount']}"


async def test_by_merchant_sorted_desc(client):
    """Rows must come back sorted descending by amount."""
    with patch("finlytics.db.queries.get_by_merchant", new_callable=AsyncMock) as mock:
        mock.return_value = _BY_MERCHANT
        resp = await client.get("/api/summary/by-merchant")

    amounts = [r["amount"] for r in resp.json()]
    assert amounts == sorted(amounts, reverse=True)


async def test_by_merchant_empty(client):
    with patch("finlytics.db.queries.get_by_merchant", new_callable=AsyncMock) as mock:
        mock.return_value = []
        resp = await client.get("/api/summary/by-merchant")

    assert resp.status_code == 200
    assert resp.json() == []


async def test_by_merchant_passes_date_and_account_filters(client):
    with patch("finlytics.db.queries.get_by_merchant", new_callable=AsyncMock) as mock:
        mock.return_value = []
        resp = await client.get(
            "/api/summary/by-merchant?from=2024-01-01&to=2024-06-30&account_id=3"
        )

    assert resp.status_code == 200
    _, kwargs = mock.call_args
    assert kwargs["from_date"] == date(2024, 1, 1)
    assert kwargs["to_date"] == date(2024, 6, 30)
    assert kwargs["account_id"] == 3


async def test_by_merchant_tag_filter_passed(client):
    with patch("finlytics.db.queries.get_by_merchant", new_callable=AsyncMock) as mock:
        mock.return_value = []
        resp = await client.get("/api/summary/by-merchant?tag=supermercado")

    assert resp.status_code == 200
    _, kwargs = mock.call_args
    assert kwargs["tags"] == ["supermercado"]


async def test_by_merchant_multi_tag_passed(client):
    with patch("finlytics.db.queries.get_by_merchant", new_callable=AsyncMock) as mock:
        mock.return_value = []
        resp = await client.get("/api/summary/by-merchant?tag=luz&tag=agua")

    assert resp.status_code == 200
    _, kwargs = mock.call_args
    assert set(kwargs["tags"]) == {"luz", "agua"}


async def test_by_merchant_flow_filter_passed(client):
    with patch("finlytics.db.queries.get_by_merchant", new_callable=AsyncMock) as mock:
        mock.return_value = []
        resp = await client.get("/api/summary/by-merchant?flow=expense")

    assert resp.status_code == 200
    _, kwargs = mock.call_args
    assert kwargs["flow"] == "expense"


async def test_by_merchant_flow_invalid_returns_422(client):
    resp = await client.get("/api/summary/by-merchant?flow=transfer")
    assert resp.status_code == 422


async def test_by_merchant_tag_none_when_not_provided(client):
    with patch("finlytics.db.queries.get_by_merchant", new_callable=AsyncMock) as mock:
        mock.return_value = []
        await client.get("/api/summary/by-merchant")

    _, kwargs = mock.call_args
    assert kwargs["tags"] is None


async def test_by_merchant_flow_none_when_not_provided(client):
    with patch("finlytics.db.queries.get_by_merchant", new_callable=AsyncMock) as mock:
        mock.return_value = []
        await client.get("/api/summary/by-merchant")

    _, kwargs = mock.call_args
    assert kwargs["flow"] is None


# ── Cross-filter: merchant on by-category ────────────────────────────────────

async def test_by_category_merchant_filter_forwarded(client):
    """?merchant=Mercadona is forwarded to get_by_category."""
    with patch("finlytics.db.queries.get_by_category", new_callable=AsyncMock) as mock:
        mock.return_value = _BY_CATEGORY
        resp = await client.get("/api/summary/by-category?merchant=Mercadona")

    assert resp.status_code == 200
    _, kwargs = mock.call_args
    assert kwargs["merchant"] == "Mercadona"


async def test_by_category_merchant_none_when_not_provided(client):
    with patch("finlytics.db.queries.get_by_category", new_callable=AsyncMock) as mock:
        mock.return_value = []
        await client.get("/api/summary/by-category")

    _, kwargs = mock.call_args
    assert kwargs["merchant"] is None


async def test_by_category_merchant_narrows_results(client):
    """A merchant cross-filter returns only that merchant's category totals."""
    filtered = [{"category_id": 1, "category": "Groceries", "amount": 140.0, "count": 5}]
    with patch("finlytics.db.queries.get_by_category", new_callable=AsyncMock) as mock:
        mock.return_value = filtered
        resp = await client.get("/api/summary/by-category?merchant=Mercadona")

    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["category"] == "Groceries"
    _, kwargs = mock.call_args
    assert kwargs["merchant"] == "Mercadona"


# ── Cross-filter: day on by-category ─────────────────────────────────────────

async def test_by_category_day_filter_forwarded(client):
    """?day=2024-05-10 is forwarded to get_by_category."""
    with patch("finlytics.db.queries.get_by_category", new_callable=AsyncMock) as mock:
        mock.return_value = []
        resp = await client.get("/api/summary/by-category?day=2024-05-10")

    assert resp.status_code == 200
    _, kwargs = mock.call_args
    assert kwargs["day"] == date(2024, 5, 10)


async def test_by_category_day_none_when_not_provided(client):
    with patch("finlytics.db.queries.get_by_category", new_callable=AsyncMock) as mock:
        mock.return_value = []
        await client.get("/api/summary/by-category")

    _, kwargs = mock.call_args
    assert kwargs["day"] is None


async def test_by_category_day_narrows_results(client):
    """?day= returns only that day's category totals."""
    filtered = [{"category_id": 2, "category": "Dining", "amount": 30.0, "count": 1}]
    with patch("finlytics.db.queries.get_by_category", new_callable=AsyncMock) as mock:
        mock.return_value = filtered
        resp = await client.get("/api/summary/by-category?day=2024-06-03")

    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["category"] == "Dining"
    _, kwargs = mock.call_args
    assert kwargs["day"] == date(2024, 6, 3)


# ── Cross-filter: merchant on by-day ─────────────────────────────────────────

async def test_by_day_merchant_filter_forwarded(client):
    """?merchant=Netflix is forwarded to get_by_day."""
    with patch("finlytics.db.queries.get_by_day", new_callable=AsyncMock) as mock:
        mock.return_value = []
        resp = await client.get("/api/summary/by-day?merchant=Netflix")

    assert resp.status_code == 200
    _, kwargs = mock.call_args
    assert kwargs["merchant"] == "Netflix"


async def test_by_day_merchant_none_when_not_provided(client):
    with patch("finlytics.db.queries.get_by_day", new_callable=AsyncMock) as mock:
        mock.return_value = []
        await client.get("/api/summary/by-day")

    _, kwargs = mock.call_args
    assert kwargs["merchant"] is None


async def test_by_day_merchant_narrows_results(client):
    """?merchant= returns only that merchant's daily totals."""
    filtered = [{"day": "2024-05-10", "expense": 14.99, "income": 0.0, "net": -14.99}]
    with patch("finlytics.db.queries.get_by_day", new_callable=AsyncMock) as mock:
        mock.return_value = filtered
        resp = await client.get("/api/summary/by-day?merchant=Netflix")

    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["day"] == "2024-05-10"
    _, kwargs = mock.call_args
    assert kwargs["merchant"] == "Netflix"


# ── Cross-filter: category_id on by-merchant ─────────────────────────────────

async def test_by_merchant_category_id_filter_forwarded(client):
    """?category_id=1 is forwarded to get_by_merchant."""
    with patch("finlytics.db.queries.get_by_merchant", new_callable=AsyncMock) as mock:
        mock.return_value = _BY_MERCHANT
        resp = await client.get("/api/summary/by-merchant?category_id=1")

    assert resp.status_code == 200
    _, kwargs = mock.call_args
    assert kwargs["category_id"] == 1


async def test_by_merchant_category_id_none_when_not_provided(client):
    with patch("finlytics.db.queries.get_by_merchant", new_callable=AsyncMock) as mock:
        mock.return_value = []
        await client.get("/api/summary/by-merchant")

    _, kwargs = mock.call_args
    assert kwargs["category_id"] is None


async def test_by_merchant_category_id_narrows_results(client):
    """?category_id=N returns only merchants that appear in that category."""
    filtered = [{"merchant": "Mercadona", "amount": 240.0, "count": 8}]
    with patch("finlytics.db.queries.get_by_merchant", new_callable=AsyncMock) as mock:
        mock.return_value = filtered
        resp = await client.get("/api/summary/by-merchant?category_id=1")

    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["merchant"] == "Mercadona"
    _, kwargs = mock.call_args
    assert kwargs["category_id"] == 1


# ── Cross-filter: day on by-merchant ─────────────────────────────────────────

async def test_by_merchant_day_filter_forwarded(client):
    """?day=2024-05-10 is forwarded to get_by_merchant."""
    with patch("finlytics.db.queries.get_by_merchant", new_callable=AsyncMock) as mock:
        mock.return_value = []
        resp = await client.get("/api/summary/by-merchant?day=2024-05-10")

    assert resp.status_code == 200
    _, kwargs = mock.call_args
    assert kwargs["day"] == date(2024, 5, 10)


async def test_by_merchant_day_none_when_not_provided(client):
    with patch("finlytics.db.queries.get_by_merchant", new_callable=AsyncMock) as mock:
        mock.return_value = []
        await client.get("/api/summary/by-merchant")

    _, kwargs = mock.call_args
    assert kwargs["day"] is None


async def test_by_merchant_day_narrows_results(client):
    """?day= returns only merchants with transactions on that day."""
    filtered = [{"merchant": "Netflix", "amount": 14.99, "count": 1}]
    with patch("finlytics.db.queries.get_by_merchant", new_callable=AsyncMock) as mock:
        mock.return_value = filtered
        resp = await client.get("/api/summary/by-merchant?day=2024-06-03")

    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["merchant"] == "Netflix"
    _, kwargs = mock.call_args
    assert kwargs["day"] == date(2024, 6, 3)


# ── Cross-filter: day on overview ────────────────────────────────────────────

async def test_overview_day_filter_forwarded(client):
    """?day=2024-05-10 is forwarded to get_overview."""
    with patch("finlytics.db.queries.get_overview", new_callable=AsyncMock) as mock:
        mock.return_value = _OVERVIEW
        resp = await client.get("/api/summary/overview?day=2024-05-10")

    assert resp.status_code == 200
    _, kwargs = mock.call_args
    assert kwargs["day"] == date(2024, 5, 10)


async def test_overview_day_none_when_not_provided(client):
    with patch("finlytics.db.queries.get_overview", new_callable=AsyncMock) as mock:
        mock.return_value = _OVERVIEW
        await client.get("/api/summary/overview")

    _, kwargs = mock.call_args
    assert kwargs["day"] is None


async def test_overview_day_narrows_totals(client):
    """?day= narrows totals to a single day's transactions."""
    day_filtered = {
        **_OVERVIEW,
        "total_expense": 50.0,
        "total_income": 0.0,
        "net": -50.0,
        "num_transactions": 2,
        "top_category": {"name": "Groceries", "amount": 50.0},
    }
    with patch("finlytics.db.queries.get_overview", new_callable=AsyncMock) as mock:
        mock.return_value = day_filtered
        resp = await client.get("/api/summary/overview?day=2024-05-10")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total_expense"] == 50.0
    assert body["num_transactions"] == 2
    _, kwargs = mock.call_args
    assert kwargs["day"] == date(2024, 5, 10)
