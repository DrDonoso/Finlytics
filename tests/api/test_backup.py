"""Tests for GET /api/backup/export and POST /api/backup/import.

Strategy
────────
* Export tests mock session.execute with a deterministic side_effect list that
  matches the exact query order in backup.py, then verify the JSON shape.
* Import tests use a purpose-built session fixture (_make_autoincrement_session)
  that assigns incrementing IDs on flush, enabling full end-to-end import
  verification without a live database.
* translate guard tests patch finlytics.db.repository.translate_category_name
  and assert it is never called during restore.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from finlytics.api.deps import get_current_user, get_db
from finlytics.app import app


# ── Mock-result helpers ───────────────────────────────────────────────────────


def _scalar_none():
    """execute() result where scalar_one_or_none() returns None."""
    m = MagicMock()
    m.scalar_one_or_none.return_value = None
    return m


def _scalar_value(v):
    """execute() result where scalar_one_or_none() returns v."""
    m = MagicMock()
    m.scalar_one_or_none.return_value = v
    return m


def _scalars_all(*items):
    """execute() result where scalars().all() returns items."""
    m = MagicMock()
    m.scalars.return_value.all.return_value = list(items)
    return m


def _mappings_all(*rows):
    """execute() result where mappings().all() returns rows (plain dicts)."""
    m = MagicMock()
    m.mappings.return_value.all.return_value = list(rows)
    return m


def _rows_all(*rows):
    """execute() result where .all() returns rows."""
    m = MagicMock()
    m.all.return_value = list(rows)
    return m


# ── Session fixture with auto-incrementing IDs on flush ───────────────────────


def _make_autoincrement_session():
    """Return a mock AsyncSession that assigns sequential IDs to added objects.

    Simulates the RDBMS behaviour of populating primary keys on INSERT by
    iterating through pending objects in each flush() call and setting
    obj.id = <next integer> when the field is currently None.
    """
    session = MagicMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.close = AsyncMock()

    _counter = [0]
    _pending: list = []

    def _add(obj):
        _pending.append(obj)

    session.add = _add

    async def _flush():
        for obj in _pending:
            if getattr(obj, "id", None) is None:
                _counter[0] += 1
                obj.id = _counter[0]
        _pending.clear()

    session.flush = AsyncMock(side_effect=_flush)

    begin_cm = AsyncMock()
    session.begin = MagicMock(return_value=begin_cm)
    return session


@pytest.fixture
def auto_session():
    return _make_autoincrement_session()


@pytest.fixture
async def import_client(auto_session):
    """HTTP client wired to the autoincrement session + a stub current user."""

    async def _get_db():
        yield auto_session

    async def _get_user():
        return MagicMock(username="testuser")

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_current_user] = _get_user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c, auto_session
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)


# ── Shared payload ────────────────────────────────────────────────────────────

_VALID_BACKUP = {
    "finlytics_backup_version": 1,
    "exported_at": "2026-01-01T00:00:00+00:00",
    "accounts": [{"name": "BBVA", "type": "bank", "currency": "EUR"}],
    "categories": [
        {"name": "Groceries", "is_base": True, "color": "#22c55e", "name_es": "Compras"}
    ],
    "tags": [{"name": "food", "color": "#ff0000", "emoji": "🍎"}],
    "transactions": [
        {
            "transaction_date": "2024-06-01",
            "amount": -42.5,
            "currency": "EUR",
            "description": "MERCADONA",
            "merchant": None,
            "category": "Groceries",
            "account": "BBVA",
            "category_confidence": 0.97,
            "balance_after": None,
            "tags": ["food"],
        }
    ],
}


# ── Export tests ──────────────────────────────────────────────────────────────


async def test_export_returns_200(client, mock_session):
    acc = MagicMock(); acc.name = "BBVA"; acc.type = "bank"; acc.currency = "EUR"
    cat = MagicMock(); cat.name = "Groceries"; cat.is_base = True
    cat.color = "#22c55e"; cat.name_es = "Compras"
    tag = MagicMock(); tag.name = "food"; tag.color = "#ff0000"; tag.emoji = "🍎"

    tx_row = {
        "id": 1, "transaction_date": date(2024, 6, 1),
        "amount": Decimal("-42.50"), "currency": "EUR",
        "description": "MERCADONA", "merchant": None,
        "category_confidence": 0.97, "balance_after": None,
        "category_name": "Groceries", "account_name": "BBVA",
    }

    mock_session.execute.side_effect = [
        _scalars_all(acc),          # accounts
        _scalars_all(cat),          # categories
        _scalars_all(tag),          # tags
        _mappings_all(tx_row),      # transactions
        _rows_all((1, "food")),     # tag map
    ]

    resp = await client.get("/api/backup/export")
    assert resp.status_code == 200


async def test_export_has_required_top_level_keys(client, mock_session):
    mock_session.execute.side_effect = [
        _scalars_all(),   # accounts: empty
        _scalars_all(),   # categories: empty
        _scalars_all(),   # tags: empty
        _mappings_all(),  # transactions: empty
        # no tag-map query (tx_ids is empty)
    ]

    resp = await client.get("/api/backup/export")
    body = resp.json()

    assert set(body.keys()) == {
        "finlytics_backup_version", "exported_at",
        "accounts", "categories", "tags", "transactions",
    }
    assert body["finlytics_backup_version"] == 1
    assert body["exported_at"]  # non-empty ISO string


async def test_export_account_fields(client, mock_session):
    acc = MagicMock(); acc.name = "BBVA"; acc.type = "bank"; acc.currency = "EUR"

    mock_session.execute.side_effect = [
        _scalars_all(acc),
        _scalars_all(),
        _scalars_all(),
        _mappings_all(),
    ]

    body = (await client.get("/api/backup/export")).json()
    assert body["accounts"] == [{"name": "BBVA", "type": "bank", "currency": "EUR"}]


async def test_export_category_fields(client, mock_session):
    cat = MagicMock()
    cat.name = "Groceries"; cat.is_base = True
    cat.color = "#22c55e"; cat.name_es = "Compras"

    mock_session.execute.side_effect = [
        _scalars_all(),
        _scalars_all(cat),
        _scalars_all(),
        _mappings_all(),
    ]

    body = (await client.get("/api/backup/export")).json()
    assert body["categories"] == [
        {"name": "Groceries", "is_base": True, "color": "#22c55e", "name_es": "Compras"}
    ]


async def test_export_tag_fields(client, mock_session):
    tag = MagicMock(); tag.name = "food"; tag.color = "#ff0000"; tag.emoji = "🍎"

    mock_session.execute.side_effect = [
        _scalars_all(),
        _scalars_all(),
        _scalars_all(tag),
        _mappings_all(),
    ]

    body = (await client.get("/api/backup/export")).json()
    assert body["tags"] == [{"name": "food", "color": "#ff0000", "emoji": "🍎"}]


async def test_export_transaction_fields(client, mock_session):
    tx_row = {
        "id": 7,
        "transaction_date": date(2024, 6, 15),
        "amount": Decimal("-99.00"),
        "currency": "EUR",
        "description": "LIDL",
        "merchant": "Lidl",
        "category_confidence": 0.85,
        "balance_after": Decimal("1000.00"),
        "category_name": "Groceries",
        "account_name": "BBVA",
    }

    mock_session.execute.side_effect = [
        _scalars_all(),
        _scalars_all(),
        _scalars_all(),
        _mappings_all(tx_row),
        _rows_all(),   # no tags
    ]

    body = (await client.get("/api/backup/export")).json()
    tx = body["transactions"][0]

    assert set(tx.keys()) == {
        "transaction_date", "amount", "currency", "description",
        "merchant", "category", "account",
        "category_confidence", "balance_after", "tags",
    }
    assert tx["transaction_date"] == "2024-06-15"
    assert tx["amount"] == pytest.approx(-99.0)
    assert tx["merchant"] == "Lidl"
    assert tx["category"] == "Groceries"
    assert tx["balance_after"] == pytest.approx(1000.0)
    assert tx["tags"] == []


async def test_export_transaction_tags_resolved(client, mock_session):
    """Tags are batch-loaded and attached to their transaction."""
    tx_row = {
        "id": 10, "transaction_date": date(2024, 7, 1),
        "amount": Decimal("-10.00"), "currency": "EUR",
        "description": "TEST", "merchant": None,
        "category_confidence": None, "balance_after": None,
        "category_name": None, "account_name": "BBVA",
    }

    mock_session.execute.side_effect = [
        _scalars_all(),
        _scalars_all(),
        _scalars_all(),
        _mappings_all(tx_row),
        _rows_all((10, "alfa"), (10, "beta")),
    ]

    body = (await client.get("/api/backup/export")).json()
    assert body["transactions"][0]["tags"] == ["alfa", "beta"]


async def test_export_content_disposition_header(client, mock_session):
    mock_session.execute.side_effect = [
        _scalars_all(), _scalars_all(), _scalars_all(), _mappings_all(),
    ]
    resp = await client.get("/api/backup/export")
    cd = resp.headers.get("content-disposition", "")
    assert "attachment" in cd
    assert "finlytics-backup-" in cd
    assert ".json" in cd


async def test_export_handles_empty_db(client, mock_session):
    mock_session.execute.side_effect = [
        _scalars_all(), _scalars_all(), _scalars_all(), _mappings_all(),
    ]
    body = (await client.get("/api/backup/export")).json()
    assert body["accounts"] == []
    assert body["categories"] == []
    assert body["tags"] == []
    assert body["transactions"] == []


# ── Import — validation ───────────────────────────────────────────────────────


async def test_import_unknown_version_returns_400(client):
    payload = {**_VALID_BACKUP, "finlytics_backup_version": 99}
    resp = await client.post("/api/backup/import", json=payload)
    assert resp.status_code == 400
    assert "99" in resp.json()["detail"]


async def test_import_version_0_returns_400(client):
    payload = {**_VALID_BACKUP, "finlytics_backup_version": 0}
    resp = await client.post("/api/backup/import", json=payload)
    assert resp.status_code == 400


async def test_import_response_shape(import_client):
    """POST /api/backup/import returns an ImportSummary with all expected keys."""
    client, session = import_client
    session.execute.side_effect = [
        _scalar_none(),      # account lookup → not found
        _scalar_none(),      # category lookup → not found
        _scalar_none(),      # tag lookup → not found
        _scalar_value(42),   # transaction insert → new (id=42)
        MagicMock(),         # transaction_tags insert
    ]

    resp = await client.post("/api/backup/import", json=_VALID_BACKUP)
    assert resp.status_code == 200

    body = resp.json()
    assert set(body.keys()) == {
        "accounts_created", "accounts_existing",
        "categories_created", "categories_updated",
        "tags_created", "tags_updated",
        "transactions_inserted", "transactions_duplicates",
    }


async def test_import_creates_new_objects(import_client):
    """Fresh import: all objects are created; counts reflect inserts."""
    client, session = import_client
    session.execute.side_effect = [
        _scalar_none(),      # account lookup → not found
        _scalar_none(),      # category lookup → not found
        _scalar_none(),      # tag lookup → not found
        _scalar_value(42),   # transaction insert → new
        MagicMock(),         # transaction_tags insert
    ]

    resp = await client.post("/api/backup/import", json=_VALID_BACKUP)
    body = resp.json()

    assert body["accounts_created"] == 1
    assert body["accounts_existing"] == 0
    assert body["categories_created"] == 1
    assert body["categories_updated"] == 0
    assert body["tags_created"] == 1
    assert body["tags_updated"] == 0
    assert body["transactions_inserted"] == 1
    assert body["transactions_duplicates"] == 0


async def test_import_idempotent_second_run(import_client):
    """Re-importing the same backup: accounts/categories/tags updated, tx deduplicated."""
    client, session = import_client

    mock_acc = MagicMock(); mock_acc.id = 1; mock_acc.name = "BBVA"
    mock_cat = MagicMock(); mock_cat.id = 2; mock_cat.name = "Groceries"
    mock_cat.color = "#22c55e"; mock_cat.name_es = "Compras"
    mock_tag = MagicMock(); mock_tag.id = 3; mock_tag.name = "food"
    mock_tag.color = "#ff0000"; mock_tag.emoji = "🍎"

    session.execute.side_effect = [
        _scalar_value(mock_acc),    # account lookup → found
        _scalar_value(mock_cat),    # category lookup → found (updates color/name_es)
        _scalar_value(mock_tag),    # tag lookup → found (updates color/emoji)
        _scalar_value(None),        # transaction insert → conflict (duplicate)
    ]

    resp = await client.post("/api/backup/import", json=_VALID_BACKUP)
    body = resp.json()

    assert body["accounts_created"] == 0
    assert body["accounts_existing"] == 1
    assert body["categories_created"] == 0
    assert body["categories_updated"] == 1
    assert body["tags_created"] == 0
    assert body["tags_updated"] == 1
    assert body["transactions_inserted"] == 0
    assert body["transactions_duplicates"] == 1


async def test_import_category_upsert_updates_color_and_name_es(import_client):
    """Existing category gets its color and name_es updated from the backup."""
    client, session = import_client

    mock_cat = MagicMock(); mock_cat.id = 5
    mock_cat.name = "Groceries"; mock_cat.color = "#000000"; mock_cat.name_es = None

    session.execute.side_effect = [
        _scalar_none(),             # account lookup → not found
        _scalar_value(mock_cat),    # category lookup → found
        _scalar_none(),             # tag lookup → not found
        _scalar_value(10),          # transaction insert → new
        MagicMock(),                # transaction_tags insert
    ]

    await client.post("/api/backup/import", json=_VALID_BACKUP)

    # Category was updated in-place
    assert mock_cat.color == "#22c55e"
    assert mock_cat.name_es == "Compras"


async def test_import_category_no_translate_called(import_client):
    """translate_category_name must NEVER be called during backup restore."""
    client, session = import_client
    session.execute.side_effect = [
        _scalar_none(),     # account
        _scalar_none(),     # category
        _scalar_none(),     # tag
        _scalar_value(99),  # transaction
        MagicMock(),        # transaction_tags
    ]

    with patch(
        "finlytics.db.repository.translate_category_name",
        new_callable=AsyncMock,
    ) as mock_translate:
        await client.post("/api/backup/import", json=_VALID_BACKUP)
        mock_translate.assert_not_called()


async def test_import_tag_upsert_updates_color_and_emoji(import_client):
    """Existing tag gets its color and emoji updated from the backup."""
    client, session = import_client

    mock_tag = MagicMock(); mock_tag.id = 7
    mock_tag.name = "food"; mock_tag.color = "#000000"; mock_tag.emoji = None

    session.execute.side_effect = [
        _scalar_none(),             # account
        _scalar_none(),             # category
        _scalar_value(mock_tag),    # tag lookup → found
        _scalar_value(20),          # transaction
        MagicMock(),                # transaction_tags
    ]

    await client.post("/api/backup/import", json=_VALID_BACKUP)

    assert mock_tag.color == "#ff0000"
    assert mock_tag.emoji == "🍎"


async def test_import_transaction_only_tag_created(import_client):
    """A tag referenced only in a transaction's tags list is silently created."""
    client, session = import_client

    payload = {
        **_VALID_BACKUP,
        "tags": [],  # body.tags is empty — "newtag" only exists in the transaction
        "transactions": [
            {
                **_VALID_BACKUP["transactions"][0],
                "tags": ["newtag"],  # not in body.tags
            }
        ],
    }

    session.execute.side_effect = [
        _scalar_none(),     # account lookup
        _scalar_none(),     # category lookup
        # no tag loop (body.tags empty)
        _scalar_value(55),  # transaction insert → new
        _scalar_none(),     # get_or_create_tag: Tag lookup for "newtag" → not found
        MagicMock(),        # transaction_tags insert
    ]

    resp = await client.post("/api/backup/import", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["transactions_inserted"] == 1
    # silently created; not counted in tags_created/tags_updated
    assert body["tags_created"] == 0
    assert body["tags_updated"] == 0


async def test_import_empty_backup_returns_zeros(import_client):
    """An empty backup (no data) succeeds with all-zero counts."""
    client, _ = import_client

    payload = {
        "finlytics_backup_version": 1,
        "exported_at": "2026-01-01T00:00:00+00:00",
        "accounts": [],
        "categories": [],
        "tags": [],
        "transactions": [],
    }

    resp = await client.post("/api/backup/import", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert all(v == 0 for v in body.values())


async def test_import_multiple_accounts(import_client):
    """Multiple accounts in a backup are all created."""
    client, session = import_client

    payload = {
        **_VALID_BACKUP,
        "accounts": [
            {"name": "BBVA",  "type": "bank",   "currency": "EUR"},
            {"name": "Monzo", "type": "bank",   "currency": "GBP"},
        ],
        "transactions": [
            {**_VALID_BACKUP["transactions"][0], "account": "BBVA"},
        ],
    }

    session.execute.side_effect = [
        _scalar_none(),     # BBVA account lookup
        _scalar_none(),     # Monzo account lookup
        _scalar_none(),     # category lookup
        _scalar_none(),     # tag lookup
        _scalar_value(77),  # transaction insert
        MagicMock(),        # transaction_tags
    ]

    resp = await client.post("/api/backup/import", json=payload)
    body = resp.json()
    assert body["accounts_created"] == 2
    assert body["transactions_inserted"] == 1


# ── Round-trip test ───────────────────────────────────────────────────────────


async def test_roundtrip_export_then_import(client, mock_session):
    """Seed data → export → import on a fresh DB reproduces all entity counts."""
    # ── Phase 1: export ───────────────────────────────────────────────────────
    acc = MagicMock(); acc.name = "BBVA"; acc.type = "bank"; acc.currency = "EUR"
    cat = MagicMock(); cat.name = "Groceries"; cat.is_base = True
    cat.color = "#22c55e"; cat.name_es = "Compras"
    tag = MagicMock(); tag.name = "food"; tag.color = "#ff0000"; tag.emoji = "🍎"
    tx_row = {
        "id": 100,
        "transaction_date": date(2024, 6, 1),
        "amount": Decimal("-42.50"),
        "currency": "EUR",
        "description": "MERCADONA",
        "merchant": None,
        "category_confidence": 0.97,
        "balance_after": None,
        "category_name": "Groceries",
        "account_name": "BBVA",
    }

    mock_session.execute.side_effect = [
        _scalars_all(acc),
        _scalars_all(cat),
        _scalars_all(tag),
        _mappings_all(tx_row),
        _rows_all((100, "food")),
    ]

    export_resp = await client.get("/api/backup/export")
    assert export_resp.status_code == 200
    backup_json = export_resp.json()

    # Verify the exported payload matches the spec contract
    assert backup_json["finlytics_backup_version"] == 1
    assert len(backup_json["accounts"]) == 1
    assert len(backup_json["categories"]) == 1
    assert len(backup_json["tags"]) == 1
    assert len(backup_json["transactions"]) == 1
    assert backup_json["transactions"][0]["tags"] == ["food"]

    # ── Phase 2: import the export JSON into a fresh (empty) DB ──────────────
    auto_sess = _make_autoincrement_session()
    auto_sess.execute.side_effect = [
        _scalar_none(),     # account lookup
        _scalar_none(),     # category lookup
        _scalar_none(),     # tag lookup
        _scalar_value(42),  # transaction insert → new
        MagicMock(),        # transaction_tags
    ]

    async def _fresh_db():
        yield auto_sess

    async def _stub_user():
        return MagicMock(username="testuser")

    app.dependency_overrides[get_db] = _fresh_db
    app.dependency_overrides[get_current_user] = _stub_user
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as import_c:
            import_resp = await import_c.post("/api/backup/import", json=backup_json)
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)

    assert import_resp.status_code == 200
    summary = import_resp.json()
    assert summary["accounts_created"] == 1
    assert summary["categories_created"] == 1
    assert summary["tags_created"] == 1
    assert summary["transactions_inserted"] == 1
    assert summary["transactions_duplicates"] == 0
