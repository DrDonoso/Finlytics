"""Tests for GET /api/transactions and PATCH /api/transactions/{id}."""

from datetime import date
from unittest.mock import AsyncMock, patch

from finlytics.db.queries import DedupCollisionError


_TX = {
    "id": 1,
    "transaction_date": "2024-06-01",
    "amount": -42.5,
    "currency": "EUR",
    "description": "MERCADONA",
    "category": "Groceries",
    "account": "BBVA",
    "category_confidence": 0.97,
    "balance_after": 1200.0,
    "tags": [],
    "merchant": None,
    "detail": None,
}


async def test_list_transactions_basic(client):
    with patch("finlytics.db.queries.get_transactions", new_callable=AsyncMock) as mock:
        mock.return_value = ([_TX], 1)
        resp = await client.get("/api/transactions")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1


async def test_transaction_schema_fields(client):
    with patch("finlytics.db.queries.get_transactions", new_callable=AsyncMock) as mock:
        mock.return_value = ([_TX], 1)
        resp = await client.get("/api/transactions")

    item = resp.json()["items"][0]
    expected_keys = {
        "id", "transaction_date", "amount", "currency", "description",
        "category", "account", "category_confidence", "balance_after", "tags",
        "merchant", "detail",
    }
    assert set(item.keys()) == expected_keys


async def test_transactions_pagination_fields(client):
    with patch("finlytics.db.queries.get_transactions", new_callable=AsyncMock) as mock:
        mock.return_value = ([], 0)
        resp = await client.get("/api/transactions?limit=10&offset=20")

    body = resp.json()
    assert body["limit"] == 10
    assert body["offset"] == 20
    assert body["total"] == 0


async def test_transactions_passes_filters_to_query(client):
    with patch("finlytics.db.queries.get_transactions", new_callable=AsyncMock) as mock:
        mock.return_value = ([], 0)
        resp = await client.get(
            "/api/transactions?from=2024-01-01&to=2024-12-31&account_id=1&category_id=2"
        )

    assert resp.status_code == 200
    _, kwargs = mock.call_args
    assert kwargs["from_date"] == date(2024, 1, 1)
    assert kwargs["to_date"] == date(2024, 12, 31)
    assert kwargs["account_id"] == 1
    assert kwargs["category_id"] == 2


async def test_transactions_optional_fields_null(client):
    tx_no_optionals = {**_TX, "category_confidence": None, "balance_after": None}
    with patch("finlytics.db.queries.get_transactions", new_callable=AsyncMock) as mock:
        mock.return_value = ([tx_no_optionals], 1)
        resp = await client.get("/api/transactions")

    item = resp.json()["items"][0]
    assert item["category_confidence"] is None
    assert item["balance_after"] is None


async def test_transactions_signed_amount(client):
    """amount must be a JSON number (negative for expenses)."""
    with patch("finlytics.db.queries.get_transactions", new_callable=AsyncMock) as mock:
        mock.return_value = ([_TX], 1)
        resp = await client.get("/api/transactions")

    amount = resp.json()["items"][0]["amount"]
    assert isinstance(amount, float)
    assert amount < 0


# ── PATCH /api/transactions/{id} ─────────────────────────────────────────────

async def test_patch_partial_description(client):
    updated = {**_TX, "description": "LIDL"}
    with patch("finlytics.db.queries.update_transaction", new_callable=AsyncMock) as mock:
        mock.return_value = updated
        resp = await client.patch("/api/transactions/1", json={"description": "LIDL"})

    assert resp.status_code == 200
    assert resp.json()["description"] == "LIDL"


async def test_patch_partial_amount(client):
    updated = {**_TX, "amount": -99.0}
    with patch("finlytics.db.queries.update_transaction", new_callable=AsyncMock) as mock:
        mock.return_value = updated
        resp = await client.patch("/api/transactions/1", json={"amount": -99.0})

    assert resp.status_code == 200
    assert resp.json()["amount"] == -99.0
    # Verify the new amount was forwarded so update_transaction recomputes dedup_hash
    _, kwargs = mock.call_args
    assert kwargs["amount"] == -99.0


async def test_patch_partial_category(client):
    updated = {**_TX, "category": "Dining"}
    with patch("finlytics.db.queries.update_transaction", new_callable=AsyncMock) as mock:
        mock.return_value = updated
        resp = await client.patch("/api/transactions/1", json={"category": "Dining"})

    assert resp.status_code == 200
    assert resp.json()["category"] == "Dining"


async def test_patch_all_three_fields(client):
    updated = {**_TX, "description": "CARREFOUR", "amount": -55.0, "category": "Groceries"}
    with patch("finlytics.db.queries.update_transaction", new_callable=AsyncMock) as mock:
        mock.return_value = updated
        resp = await client.patch(
            "/api/transactions/1",
            json={"description": "CARREFOUR", "amount": -55.0, "category": "Groceries"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["description"] == "CARREFOUR"
    assert body["amount"] == -55.0
    assert body["category"] == "Groceries"


async def test_patch_404_missing_transaction(client):
    with patch("finlytics.db.queries.update_transaction", new_callable=AsyncMock) as mock:
        mock.return_value = None
        resp = await client.patch("/api/transactions/999", json={"description": "X"})

    assert resp.status_code == 404


async def test_patch_409_dedup_collision(client):
    with patch("finlytics.db.queries.update_transaction", new_callable=AsyncMock) as mock:
        mock.side_effect = DedupCollisionError("Transaction id=7 already has the same account, date, amount, and description.")
        resp = await client.patch("/api/transactions/1", json={"amount": -50.0})

    assert resp.status_code == 409
    assert "already" in resp.json()["detail"].lower()


async def test_patch_dedup_recomputed_on_description_change(client):
    """When description changes, update_transaction receives it → dedup_hash will be recomputed inside."""
    updated = {**_TX, "description": "NEW DESC"}
    with patch("finlytics.db.queries.update_transaction", new_callable=AsyncMock) as mock:
        mock.return_value = updated
        resp = await client.patch("/api/transactions/1", json={"description": "NEW DESC"})

    assert resp.status_code == 200
    _, kwargs = mock.call_args
    assert kwargs["description"] == "NEW DESC"


async def test_patch_response_schema_fields(client):
    with patch("finlytics.db.queries.update_transaction", new_callable=AsyncMock) as mock:
        mock.return_value = _TX
        resp = await client.patch("/api/transactions/1", json={"amount": -42.5})

    assert resp.status_code == 200
    assert set(resp.json().keys()) == {
        "id", "transaction_date", "amount", "currency", "description",
        "category", "account", "category_confidence", "balance_after", "tags",
        "merchant", "detail",
    }


async def test_patch_category_only_does_not_change_dedup(client):
    """A category-only PATCH must not raise 409; only description/amount trigger dedup."""
    updated = {**_TX, "category": "Transport"}
    with patch("finlytics.db.queries.update_transaction", new_callable=AsyncMock) as mock:
        mock.return_value = updated
        resp = await client.patch("/api/transactions/1", json={"category": "Transport"})

    assert resp.status_code == 200
    _, kwargs = mock.call_args
    # description and amount were not passed → None → no dedup recompute inside
    assert kwargs["description"] is None
    assert kwargs["amount"] is None


# ── Tags on transactions ──────────────────────────────────────────────────────

async def test_transaction_includes_tags_field(client):
    """GET /api/transactions includes a 'tags' list on every item."""
    tx_with_tags = {**_TX, "tags": ["luz", "internet"]}
    with patch("finlytics.db.queries.get_transactions", new_callable=AsyncMock) as mock:
        mock.return_value = ([tx_with_tags], 1)
        resp = await client.get("/api/transactions")

    item = resp.json()["items"][0]
    assert "tags" in item
    assert item["tags"] == ["luz", "internet"]


async def test_transaction_empty_tags_field(client):
    """Tags field defaults to empty list when no tags are attached."""
    with patch("finlytics.db.queries.get_transactions", new_callable=AsyncMock) as mock:
        mock.return_value = ([_TX], 1)
        resp = await client.get("/api/transactions")

    assert resp.json()["items"][0]["tags"] == []


async def test_transactions_tag_filter_passed(client):
    """GET /api/transactions?tag=luz forwards the tag param to the query layer as a list."""
    with patch("finlytics.db.queries.get_transactions", new_callable=AsyncMock) as mock:
        mock.return_value = ([], 0)
        resp = await client.get("/api/transactions?tag=luz")

    assert resp.status_code == 200
    _, kwargs = mock.call_args
    assert kwargs["tags"] == ["luz"]


async def test_transactions_no_tag_filter_passes_none(client):
    """When ?tag is omitted, None is forwarded (no filter)."""
    with patch("finlytics.db.queries.get_transactions", new_callable=AsyncMock) as mock:
        mock.return_value = ([], 0)
        await client.get("/api/transactions")

    _, kwargs = mock.call_args
    assert kwargs["tags"] is None


async def test_transactions_multi_tag_or_filter(client):
    """?tag=luz&tag=agua passes both tags as a list (OR semantics)."""
    with patch("finlytics.db.queries.get_transactions", new_callable=AsyncMock) as mock:
        mock.return_value = ([], 0)
        resp = await client.get("/api/transactions?tag=luz&tag=agua")

    assert resp.status_code == 200
    _, kwargs = mock.call_args
    assert set(kwargs["tags"]) == {"luz", "agua"}


async def test_patch_adds_tags(client):
    """PATCH with tags=["luz"] syncs tags and returns them in the response."""
    updated = {**_TX, "tags": ["luz"]}
    with patch("finlytics.db.queries.update_transaction", new_callable=AsyncMock) as mock:
        mock.return_value = updated
        resp = await client.patch("/api/transactions/1", json={"tags": ["luz"]})

    assert resp.status_code == 200
    assert resp.json()["tags"] == ["luz"]
    _, kwargs = mock.call_args
    assert kwargs["tags"] == ["luz"]


async def test_patch_replaces_tags(client):
    """PATCH with a new tags list replaces all existing tags."""
    updated = {**_TX, "tags": ["agua"]}
    with patch("finlytics.db.queries.update_transaction", new_callable=AsyncMock) as mock:
        mock.return_value = updated
        resp = await client.patch("/api/transactions/1", json={"tags": ["agua"]})

    assert resp.status_code == 200
    assert resp.json()["tags"] == ["agua"]


async def test_patch_clears_tags(client):
    """PATCH with tags=[] removes all tags from the transaction."""
    updated = {**_TX, "tags": []}
    with patch("finlytics.db.queries.update_transaction", new_callable=AsyncMock) as mock:
        mock.return_value = updated
        resp = await client.patch("/api/transactions/1", json={"tags": []})

    assert resp.status_code == 200
    assert resp.json()["tags"] == []
    _, kwargs = mock.call_args
    assert kwargs["tags"] == []


async def test_patch_tags_none_when_not_provided(client):
    """When 'tags' is absent from the body, None is forwarded (no tag change)."""
    with patch("finlytics.db.queries.update_transaction", new_callable=AsyncMock) as mock:
        mock.return_value = _TX
        await client.patch("/api/transactions/1", json={"description": "X"})

    _, kwargs = mock.call_args
    assert kwargs["tags"] is None


async def test_multi_tag_no_duplicate_rows(client):
    """Multi-tag OR filter returns each transaction at most once (no row multiplication)."""
    tx1 = {**_TX, "id": 1, "tags": ["luz", "agua"]}
    tx2 = {**_TX, "id": 2, "tags": ["luz"]}
    with patch("finlytics.db.queries.get_transactions", new_callable=AsyncMock) as mock:
        mock.return_value = ([tx1, tx2], 2)
        resp = await client.get("/api/transactions?tag=luz&tag=agua")

    body = resp.json()
    assert body["total"] == 2
    ids = [item["id"] for item in body["items"]]
    assert len(ids) == len(set(ids)), "Duplicate transaction IDs — row multiplication!"


# ── Flow filter ───────────────────────────────────────────────────────────────

async def test_transactions_flow_expense_filter(client):
    """?flow=expense is forwarded to get_transactions as flow='expense'."""
    with patch("finlytics.db.queries.get_transactions", new_callable=AsyncMock) as mock:
        mock.return_value = ([], 0)
        resp = await client.get("/api/transactions?flow=expense")

    assert resp.status_code == 200
    _, kwargs = mock.call_args
    assert kwargs["flow"] == "expense"


async def test_transactions_flow_income_filter(client):
    """?flow=income is forwarded to get_transactions as flow='income'."""
    with patch("finlytics.db.queries.get_transactions", new_callable=AsyncMock) as mock:
        mock.return_value = ([], 0)
        resp = await client.get("/api/transactions?flow=income")

    assert resp.status_code == 200
    _, kwargs = mock.call_args
    assert kwargs["flow"] == "income"


async def test_transactions_flow_none_when_not_provided(client):
    """When ?flow is absent, None is forwarded (no filter)."""
    with patch("finlytics.db.queries.get_transactions", new_callable=AsyncMock) as mock:
        mock.return_value = ([], 0)
        await client.get("/api/transactions")

    _, kwargs = mock.call_args
    assert kwargs["flow"] is None


async def test_transactions_flow_invalid_returns_422(client):
    """An unknown flow value returns 422."""
    resp = await client.get("/api/transactions?flow=transfer")
    assert resp.status_code == 422


async def test_transactions_flow_composes_with_account_id(client):
    """flow and account_id can both be set — both are forwarded to the query layer."""
    with patch("finlytics.db.queries.get_transactions", new_callable=AsyncMock) as mock:
        mock.return_value = ([], 0)
        resp = await client.get("/api/transactions?account_id=1&flow=expense")

    assert resp.status_code == 200
    _, kwargs = mock.call_args
    assert kwargs["account_id"] == 1
    assert kwargs["flow"] == "expense"


# ── Description / amount filters ─────────────────────────────────────────────

async def test_transactions_description_filter_forwarded(client):
    """?description=mercadona is forwarded to get_transactions."""
    with patch("finlytics.db.queries.get_transactions", new_callable=AsyncMock) as mock:
        mock.return_value = ([_TX], 1)
        resp = await client.get("/api/transactions?description=mercadona")

    assert resp.status_code == 200
    _, kwargs = mock.call_args
    assert kwargs["description"] == "mercadona"


async def test_transactions_description_case_insensitive_substring(client):
    """description filter is case-insensitive and matches substrings."""
    tx_match = {**_TX, "description": "MERCADONA SUPERMARKET"}
    with patch("finlytics.db.queries.get_transactions", new_callable=AsyncMock) as mock:
        mock.return_value = ([tx_match], 1)
        resp = await client.get("/api/transactions?description=CADONA")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert "CADONA" in body["items"][0]["description"].upper()


async def test_transactions_description_percent_treated_literally(client):
    """A '%' in the description query string is forwarded (escaped by the query layer)."""
    with patch("finlytics.db.queries.get_transactions", new_callable=AsyncMock) as mock:
        mock.return_value = ([], 0)
        resp = await client.get("/api/transactions?description=100%25")

    assert resp.status_code == 200
    _, kwargs = mock.call_args
    # FastAPI URL-decodes %25 → '%', and that literal value should reach the query layer.
    assert kwargs["description"] == "100%"


async def test_transactions_description_none_when_not_provided(client):
    """When ?description is absent, None is forwarded."""
    with patch("finlytics.db.queries.get_transactions", new_callable=AsyncMock) as mock:
        mock.return_value = ([], 0)
        await client.get("/api/transactions")

    _, kwargs = mock.call_args
    assert kwargs["description"] is None


async def test_transactions_amount_min_filter_forwarded(client):
    """?amount_min=10 is forwarded to get_transactions."""
    with patch("finlytics.db.queries.get_transactions", new_callable=AsyncMock) as mock:
        mock.return_value = ([_TX], 1)
        resp = await client.get("/api/transactions?amount_min=10")

    assert resp.status_code == 200
    _, kwargs = mock.call_args
    assert kwargs["amount_min"] == 10.0


async def test_transactions_amount_max_filter_forwarded(client):
    """?amount_max=100 is forwarded to get_transactions."""
    with patch("finlytics.db.queries.get_transactions", new_callable=AsyncMock) as mock:
        mock.return_value = ([_TX], 1)
        resp = await client.get("/api/transactions?amount_max=100")

    assert resp.status_code == 200
    _, kwargs = mock.call_args
    assert kwargs["amount_max"] == 100.0


async def test_transactions_amount_range_filter(client):
    """?amount_min and ?amount_max can both be set together."""
    with patch("finlytics.db.queries.get_transactions", new_callable=AsyncMock) as mock:
        mock.return_value = ([_TX], 1)
        resp = await client.get("/api/transactions?amount_min=10&amount_max=100")

    assert resp.status_code == 200
    _, kwargs = mock.call_args
    assert kwargs["amount_min"] == 10.0
    assert kwargs["amount_max"] == 100.0


async def test_transactions_amount_min_none_when_not_provided(client):
    """When ?amount_min is absent, None is forwarded."""
    with patch("finlytics.db.queries.get_transactions", new_callable=AsyncMock) as mock:
        mock.return_value = ([], 0)
        await client.get("/api/transactions")

    _, kwargs = mock.call_args
    assert kwargs["amount_min"] is None


async def test_transactions_amount_max_none_when_not_provided(client):
    """When ?amount_max is absent, None is forwarded."""
    with patch("finlytics.db.queries.get_transactions", new_callable=AsyncMock) as mock:
        mock.return_value = ([], 0)
        await client.get("/api/transactions")

    _, kwargs = mock.call_args
    assert kwargs["amount_max"] is None


async def test_transactions_amount_min_negative_returns_422(client):
    """A negative amount_min value returns 422 (ge=0 constraint)."""
    resp = await client.get("/api/transactions?amount_min=-5")
    assert resp.status_code == 422


async def test_transactions_amount_max_negative_returns_422(client):
    """A negative amount_max value returns 422 (ge=0 constraint)."""
    resp = await client.get("/api/transactions?amount_max=-5")
    assert resp.status_code == 422


async def test_transactions_description_and_amount_compose(client):
    """description, amount_min, and amount_max can all be used together."""
    with patch("finlytics.db.queries.get_transactions", new_callable=AsyncMock) as mock:
        mock.return_value = ([_TX], 1)
        resp = await client.get("/api/transactions?description=mercadona&amount_min=10&amount_max=100")

    assert resp.status_code == 200
    _, kwargs = mock.call_args
    assert kwargs["description"] == "mercadona"
    assert kwargs["amount_min"] == 10.0
    assert kwargs["amount_max"] == 100.0


# ── Merchant field & filter ───────────────────────────────────────────────────

async def test_transaction_merchant_field_in_response(client):
    """GET /api/transactions includes 'merchant' in every item."""
    tx_with_merchant = {**_TX, "merchant": "Mercadona"}
    with patch("finlytics.db.queries.get_transactions", new_callable=AsyncMock) as mock:
        mock.return_value = ([tx_with_merchant], 1)
        resp = await client.get("/api/transactions")

    item = resp.json()["items"][0]
    assert "merchant" in item
    assert item["merchant"] == "Mercadona"


async def test_transaction_merchant_null_when_absent(client):
    """merchant is None when the query layer returns None."""
    with patch("finlytics.db.queries.get_transactions", new_callable=AsyncMock) as mock:
        mock.return_value = ([_TX], 1)
        resp = await client.get("/api/transactions")

    assert resp.json()["items"][0]["merchant"] is None


async def test_transactions_merchant_filter_forwarded(client):
    """?merchant=amazon is forwarded to get_transactions."""
    with patch("finlytics.db.queries.get_transactions", new_callable=AsyncMock) as mock:
        mock.return_value = ([], 0)
        resp = await client.get("/api/transactions?merchant=amazon")

    assert resp.status_code == 200
    _, kwargs = mock.call_args
    assert kwargs["merchant"] == "amazon"


async def test_transactions_merchant_none_when_not_provided(client):
    """When ?merchant is absent, None is forwarded (no filter)."""
    with patch("finlytics.db.queries.get_transactions", new_callable=AsyncMock) as mock:
        mock.return_value = ([], 0)
        await client.get("/api/transactions")

    _, kwargs = mock.call_args
    assert kwargs["merchant"] is None


async def test_patch_merchant_set(client):
    """PATCH merchant='Amazon' sets merchant and is returned in the response."""
    updated = {**_TX, "merchant": "Amazon"}
    with patch("finlytics.db.queries.update_transaction", new_callable=AsyncMock) as mock:
        mock.return_value = updated
        resp = await client.patch("/api/transactions/1", json={"merchant": "Amazon"})

    assert resp.status_code == 200
    assert resp.json()["merchant"] == "Amazon"
    _, kwargs = mock.call_args
    assert kwargs["merchant"] == "Amazon"


async def test_patch_merchant_clear(client):
    """PATCH merchant='' forwards empty string (signals clear to NULL in the query layer)."""
    updated = {**_TX, "merchant": None}
    with patch("finlytics.db.queries.update_transaction", new_callable=AsyncMock) as mock:
        mock.return_value = updated
        resp = await client.patch("/api/transactions/1", json={"merchant": ""})

    assert resp.status_code == 200
    assert resp.json()["merchant"] is None
    _, kwargs = mock.call_args
    assert kwargs["merchant"] == ""


async def test_patch_merchant_none_when_not_provided(client):
    """When merchant is absent from the PATCH body, None is forwarded (no change)."""
    with patch("finlytics.db.queries.update_transaction", new_callable=AsyncMock) as mock:
        mock.return_value = _TX
        await client.patch("/api/transactions/1", json={"description": "X"})

    _, kwargs = mock.call_args
    assert kwargs["merchant"] is None


# ── Merchant filter: case-insensitive + wildcard escaping (transactions) ──────

async def test_transactions_merchant_case_insensitive_substring(client):
    """merchant filter: matching results are returned and the merchant field is serialised."""
    tx_match = {**_TX, "merchant": "Amazon Prime"}
    with patch("finlytics.db.queries.get_transactions", new_callable=AsyncMock) as mock:
        mock.return_value = ([tx_match], 1)
        resp = await client.get("/api/transactions?merchant=MAZON")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert "MAZON" in body["items"][0]["merchant"].upper()
    _, kwargs = mock.call_args
    assert kwargs["merchant"] == "MAZON"


async def test_transactions_merchant_percent_treated_literally(client):
    """A '%' in the merchant query param reaches the query layer as a literal value."""
    with patch("finlytics.db.queries.get_transactions", new_callable=AsyncMock) as mock:
        mock.return_value = ([], 0)
        resp = await client.get("/api/transactions?merchant=100%25")

    assert resp.status_code == 200
    _, kwargs = mock.call_args
    # FastAPI URL-decodes %25 → '%'; the literal '%' must be forwarded unchanged.
    assert kwargs["merchant"] == "100%"


async def test_transactions_merchant_underscore_treated_literally(client):
    """An '_' in the merchant query param is forwarded as a literal to the query layer."""
    with patch("finlytics.db.queries.get_transactions", new_callable=AsyncMock) as mock:
        mock.return_value = ([], 0)
        resp = await client.get("/api/transactions?merchant=H_M")

    assert resp.status_code == 200
    _, kwargs = mock.call_args
    assert kwargs["merchant"] == "H_M"


# ── PATCH merchant-only: dedup unaffected ─────────────────────────────────────

async def test_patch_merchant_only_does_not_trigger_dedup_recompute(client):
    """PATCH with only merchant forwards description=None and amount=None.

    In update_transaction, dedup recomputation only fires when description is
    not None or amount is not None.  A merchant-only PATCH must not set those
    fields so no hash recompute (and no risk of a spurious 409).
    """
    updated = {**_TX, "merchant": "Amazon"}
    with patch("finlytics.db.queries.update_transaction", new_callable=AsyncMock) as mock:
        mock.return_value = updated
        resp = await client.patch("/api/transactions/1", json={"merchant": "Amazon"})

    assert resp.status_code == 200
    assert resp.json()["merchant"] == "Amazon"
    _, kwargs = mock.call_args
    assert kwargs["description"] is None
    assert kwargs["amount"] is None
    assert kwargs["merchant"] == "Amazon"


# ── Dedup unaffected by merchant (unit) ───────────────────────────────────────

def test_dedup_hash_ignores_merchant():
    """Two transactions with the same natural key but different merchant values
    produce the same dedup_hash.

    Proves merchant is NOT part of the dedup key — re-importing a statement
    after a merchant correction still triggers ON CONFLICT DO NOTHING (no
    phantom duplicate rows).
    """
    from decimal import Decimal

    from finlytics.contracts import ExtractedTransaction
    from finlytics.db.repository import compute_dedup_hash

    natural_key = dict(
        account_ref="BBVA",
        transaction_date=date(2024, 6, 1),
        amount=Decimal("-42.50"),
        description="MERCADONA",
    )
    tx_with = ExtractedTransaction(**natural_key, category="Groceries", merchant="Mercadona")
    tx_without = ExtractedTransaction(**natural_key, category="Groceries", merchant=None)

    hash_with = compute_dedup_hash(
        account_ref=tx_with.account_ref,
        transaction_date=tx_with.transaction_date,
        amount=tx_with.amount,
        description=tx_with.description,
    )
    hash_without = compute_dedup_hash(
        account_ref=tx_without.account_ref,
        transaction_date=tx_without.transaction_date,
        amount=tx_without.amount,
        description=tx_without.description,
    )
    assert hash_with == hash_without, "merchant must not influence the dedup_hash"


# ── Persistence round-trip: upsert_transactions includes merchant in INSERT ────

async def test_upsert_transactions_includes_merchant_in_values():
    """upsert_transactions passes merchant=tx.merchant in the INSERT VALUES.

    Directly validates the persistence path: a merchant value from an
    ExtractedTransaction must reach the DB INSERT statement unchanged.
    """
    from decimal import Decimal
    from unittest.mock import MagicMock

    from finlytics.contracts import ExtractedTransaction
    from finlytics.db.repository import upsert_transactions

    tx = ExtractedTransaction(
        account_ref="BBVA",
        transaction_date=date(2024, 6, 1),
        amount=Decimal("-42.50"),
        description="MERCADONA",
        category="Groceries",
        merchant="Mercadona",
    )
    import_run = MagicMock(account_id=1, id=1)
    session = MagicMock()
    insert_result = MagicMock()
    insert_result.scalar_one_or_none.return_value = 99
    session.execute = AsyncMock(return_value=insert_result)
    session.flush = AsyncMock()

    captured_values: dict = {}

    with patch("finlytics.db.repository.pg_insert") as mock_pg_insert:
        mock_stmt = MagicMock()
        mock_pg_insert.return_value = mock_stmt

        def _capture_values(**kwargs):
            captured_values.update(kwargs)
            return mock_stmt

        mock_stmt.values = MagicMock(side_effect=_capture_values)
        mock_stmt.on_conflict_do_nothing = MagicMock(return_value=mock_stmt)
        mock_stmt.returning = MagicMock(return_value=mock_stmt)

        with patch(
            "finlytics.db.repository.get_or_create_category",
            new_callable=AsyncMock,
        ) as mock_cat:
            mock_cat.return_value = MagicMock(id=7)
            num_inserted, num_duplicates = await upsert_transactions(
                session, import_run, [tx]
            )

    assert captured_values.get("merchant") == "Mercadona"
    assert num_inserted == 1
    assert num_duplicates == 0


async def test_upsert_transactions_persists_merchant_none():
    """upsert_transactions passes merchant=None in INSERT when ExtractedTransaction.merchant is None.

    A transaction with no identifiable merchant (salary, transfer, ATM) must
    write NULL — not an empty string — to the merchant column.
    """
    from decimal import Decimal
    from unittest.mock import MagicMock

    from finlytics.contracts import ExtractedTransaction
    from finlytics.db.repository import upsert_transactions

    tx = ExtractedTransaction(
        account_ref="BBVA",
        transaction_date=date(2024, 6, 1),
        amount=Decimal("-99.00"),
        description="SALARY TRANSFER",
        category="Income",
        merchant=None,
    )
    import_run = MagicMock(account_id=1, id=1)
    session = MagicMock()
    insert_result = MagicMock()
    insert_result.scalar_one_or_none.return_value = 100
    session.execute = AsyncMock(return_value=insert_result)
    session.flush = AsyncMock()

    captured_values: dict = {}

    with patch("finlytics.db.repository.pg_insert") as mock_pg_insert:
        mock_stmt = MagicMock()
        mock_pg_insert.return_value = mock_stmt

        def _capture_values(**kwargs):
            captured_values.update(kwargs)
            return mock_stmt

        mock_stmt.values = MagicMock(side_effect=_capture_values)
        mock_stmt.on_conflict_do_nothing = MagicMock(return_value=mock_stmt)
        mock_stmt.returning = MagicMock(return_value=mock_stmt)

        with patch(
            "finlytics.db.repository.get_or_create_category",
            new_callable=AsyncMock,
        ) as mock_cat:
            mock_cat.return_value = MagicMock(id=3)
            num_inserted, num_duplicates = await upsert_transactions(
                session, import_run, [tx]
            )

    assert "merchant" in captured_values
    assert captured_values["merchant"] is None
    assert num_inserted == 1
    assert num_duplicates == 0


# ── Server-side sorting ───────────────────────────────────────────────────────

async def test_sort_default_is_date_desc(client):
    """Default sort (no params) uses sort_by='date', sort_dir='desc'."""
    with patch("finlytics.db.queries.get_transactions", new_callable=AsyncMock) as mock:
        mock.return_value = ([], 0)
        await client.get("/api/transactions")

    _, kwargs = mock.call_args
    assert kwargs["sort_by"] == "date"
    assert kwargs["sort_dir"] == "desc"


async def test_sort_amount_asc(client):
    """?sort=amount&order=asc forwards sort_by='amount', sort_dir='asc'."""
    with patch("finlytics.db.queries.get_transactions", new_callable=AsyncMock) as mock:
        mock.return_value = ([], 0)
        resp = await client.get("/api/transactions?sort=amount&order=asc")

    assert resp.status_code == 200
    _, kwargs = mock.call_args
    assert kwargs["sort_by"] == "amount"
    assert kwargs["sort_dir"] == "asc"


async def test_sort_amount_desc(client):
    """?sort=amount&order=desc forwards sort_by='amount', sort_dir='desc'."""
    with patch("finlytics.db.queries.get_transactions", new_callable=AsyncMock) as mock:
        mock.return_value = ([], 0)
        resp = await client.get("/api/transactions?sort=amount&order=desc")

    assert resp.status_code == 200
    _, kwargs = mock.call_args
    assert kwargs["sort_by"] == "amount"
    assert kwargs["sort_dir"] == "desc"


async def test_sort_description(client):
    """?sort=description forwards sort_by='description' with default sort_dir='desc'."""
    with patch("finlytics.db.queries.get_transactions", new_callable=AsyncMock) as mock:
        mock.return_value = ([], 0)
        resp = await client.get("/api/transactions?sort=description")

    assert resp.status_code == 200
    _, kwargs = mock.call_args
    assert kwargs["sort_by"] == "description"
    assert kwargs["sort_dir"] == "desc"


async def test_sort_merchant_asc(client):
    """?sort=merchant&order=asc forwards sort_by='merchant', sort_dir='asc'."""
    with patch("finlytics.db.queries.get_transactions", new_callable=AsyncMock) as mock:
        mock.return_value = ([], 0)
        resp = await client.get("/api/transactions?sort=merchant&order=asc")

    assert resp.status_code == 200
    _, kwargs = mock.call_args
    assert kwargs["sort_by"] == "merchant"
    assert kwargs["sort_dir"] == "asc"


async def test_sort_date_explicit(client):
    """?sort=date&order=asc forwards sort_by='date', sort_dir='asc'."""
    with patch("finlytics.db.queries.get_transactions", new_callable=AsyncMock) as mock:
        mock.return_value = ([], 0)
        resp = await client.get("/api/transactions?sort=date&order=asc")

    assert resp.status_code == 200
    _, kwargs = mock.call_args
    assert kwargs["sort_by"] == "date"
    assert kwargs["sort_dir"] == "asc"


async def test_sort_category(client):
    """?sort=category&order=asc forwards sort_by='category', sort_dir='asc'."""
    with patch("finlytics.db.queries.get_transactions", new_callable=AsyncMock) as mock:
        mock.return_value = ([], 0)
        resp = await client.get("/api/transactions?sort=category&order=asc")

    assert resp.status_code == 200
    _, kwargs = mock.call_args
    assert kwargs["sort_by"] == "category"
    assert kwargs["sort_dir"] == "asc"


async def test_sort_account(client):
    """?sort=account&order=desc forwards sort_by='account', sort_dir='desc'."""
    with patch("finlytics.db.queries.get_transactions", new_callable=AsyncMock) as mock:
        mock.return_value = ([], 0)
        resp = await client.get("/api/transactions?sort=account&order=desc")

    assert resp.status_code == 200
    _, kwargs = mock.call_args
    assert kwargs["sort_by"] == "account"
    assert kwargs["sort_dir"] == "desc"


async def test_invalid_sort_coerces_to_date_desc(client):
    """Unknown sort+order values coerce to 'date'/'desc' — no 500 or 422."""
    with patch("finlytics.db.queries.get_transactions", new_callable=AsyncMock) as mock:
        mock.return_value = ([], 0)
        resp = await client.get("/api/transactions?sort=invalid_column&order=sideways")

    assert resp.status_code == 200
    _, kwargs = mock.call_args
    assert kwargs["sort_by"] == "date"
    assert kwargs["sort_dir"] == "desc"


async def test_invalid_order_only_coerces_to_desc(client):
    """A valid sort but invalid order coerces order to 'desc'."""
    with patch("finlytics.db.queries.get_transactions", new_callable=AsyncMock) as mock:
        mock.return_value = ([], 0)
        resp = await client.get("/api/transactions?sort=amount&order=random")

    assert resp.status_code == 200
    _, kwargs = mock.call_args
    assert kwargs["sort_by"] == "amount"
    assert kwargs["sort_dir"] == "desc"


async def test_sort_order_preserved_in_full_response(client):
    """Response items appear in the order the query layer returns them (full result set)."""
    tx_a = {**_TX, "id": 10, "amount": -100.0}
    tx_b = {**_TX, "id": 20, "amount": -10.0}
    tx_c = {**_TX, "id": 30, "amount": -50.0}
    with patch("finlytics.db.queries.get_transactions", new_callable=AsyncMock) as mock:
        mock.return_value = ([tx_a, tx_b, tx_c], 3)
        resp = await client.get("/api/transactions?sort=amount&order=desc")

    body = resp.json()
    assert body["total"] == 3
    assert [item["id"] for item in body["items"]] == [10, 20, 30]


async def test_sort_composes_with_existing_filters(client):
    """sort+order compose cleanly with existing filters (account_id, flow)."""
    with patch("finlytics.db.queries.get_transactions", new_callable=AsyncMock) as mock:
        mock.return_value = ([], 0)
        resp = await client.get(
            "/api/transactions?account_id=1&flow=expense&sort=amount&order=asc"
        )

    assert resp.status_code == 200
    _, kwargs = mock.call_args
    assert kwargs["account_id"] == 1
    assert kwargs["flow"] == "expense"
    assert kwargs["sort_by"] == "amount"
    assert kwargs["sort_dir"] == "asc"
