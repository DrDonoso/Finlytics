"""Tests for GET /api/categories, POST /api/categories, and PATCH /api/categories/{id}."""

from unittest.mock import AsyncMock, MagicMock, patch

from finlytics.db.repository import get_or_create_category


_CATEGORIES = [
    {"id": 1, "name": "Groceries",          "is_base": True,  "color": "#22c55e", "name_es": "Compras",   "tx_count": 5},
    {"id": 2, "name": "Dining",             "is_base": True,  "color": "#ef4444", "name_es": "Restaurantes", "tx_count": 3},
    {"id": 3, "name": "Cosmetic Treatments","is_base": False, "color": "#64748b", "name_es": None,         "tx_count": 0},
]


# ── GET /api/categories ───────────────────────────────────────────────────────

async def test_list_categories_returns_list(client):
    with patch("finlytics.db.queries.get_categories", new_callable=AsyncMock) as mock:
        mock.return_value = _CATEGORIES
        resp = await client.get("/api/categories")

    assert resp.status_code == 200
    assert len(resp.json()) == 3


async def test_list_categories_empty(client):
    with patch("finlytics.db.queries.get_categories", new_callable=AsyncMock) as mock:
        mock.return_value = []
        resp = await client.get("/api/categories")

    assert resp.status_code == 200
    assert resp.json() == []


async def test_category_schema_fields(client):
    """Each category item has the expected fields including name_es and tx_count."""
    with patch("finlytics.db.queries.get_categories", new_callable=AsyncMock) as mock:
        mock.return_value = [_CATEGORIES[0]]
        resp = await client.get("/api/categories")

    item = resp.json()[0]
    assert set(item.keys()) == {"id", "name", "is_base", "color", "name_es", "tx_count"}
    assert item["is_base"] is True
    assert item["color"].startswith("#")


async def test_non_base_category(client):
    with patch("finlytics.db.queries.get_categories", new_callable=AsyncMock) as mock:
        mock.return_value = [_CATEGORIES[2]]
        resp = await client.get("/api/categories")

    assert resp.json()[0]["is_base"] is False


async def test_category_color_field(client):
    """color is returned for every category."""
    with patch("finlytics.db.queries.get_categories", new_callable=AsyncMock) as mock:
        mock.return_value = _CATEGORIES
        resp = await client.get("/api/categories")

    for item in resp.json():
        assert "color" in item
        assert item["color"].startswith("#")
        assert len(item["color"]) == 7


# ── PATCH /api/categories/{id} ────────────────────────────────────────────────

async def test_patch_category_color(client):
    """PATCH updates and returns the category with the new color."""
    updated = {"id": 1, "name": "Groceries", "is_base": True, "color": "#ff0000", "name_es": "Compras", "tx_count": 0}
    with patch("finlytics.db.queries.update_category", new_callable=AsyncMock) as mock:
        mock.return_value = updated
        resp = await client.patch("/api/categories/1", json={"color": "#ff0000"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["color"] == "#ff0000"
    assert body["id"] == 1
    assert body["name"] == "Groceries"


async def test_patch_category_schema_fields(client):
    """PATCH response has the same shape as GET."""
    updated = {"id": 2, "name": "Dining", "is_base": True, "color": "#00ff00", "name_es": "Restaurantes", "tx_count": 0}
    with patch("finlytics.db.queries.update_category", new_callable=AsyncMock) as mock:
        mock.return_value = updated
        resp = await client.patch("/api/categories/2", json={"color": "#00ff00"})

    assert set(resp.json().keys()) == {"id", "name", "is_base", "color", "name_es", "tx_count"}


async def test_patch_category_404(client):
    """PATCH returns 404 when the category does not exist."""
    with patch("finlytics.db.queries.update_category", new_callable=AsyncMock) as mock:
        mock.return_value = None
        resp = await client.patch("/api/categories/999", json={"color": "#ff0000"})

    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


async def test_patch_category_no_color_change(client):
    """PATCH body with no color is still accepted (no-op color update)."""
    existing = {"id": 1, "name": "Groceries", "is_base": True, "color": "#22c55e", "name_es": "Compras", "tx_count": 5}
    with patch("finlytics.db.queries.update_category", new_callable=AsyncMock) as mock:
        mock.return_value = existing
        resp = await client.patch("/api/categories/1", json={})

    assert resp.status_code == 200
    assert resp.json()["color"] == "#22c55e"


# ── POST /api/categories ──────────────────────────────────────────────────────

async def test_create_category_201(client):
    """POST creates a new category and returns 201."""
    cat = MagicMock()
    cat.id = 10
    cat.name = "Clothing"
    cat.name_es = "Ropa"
    cat.is_base = False
    cat.color = "#64748b"

    with patch("finlytics.api.categories.get_or_create_category", new_callable=AsyncMock) as mock:
        mock.return_value = cat
        resp = await client.post("/api/categories", json={"name": "Ropa"})

    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Clothing"
    assert body["name_es"] == "Ropa"
    assert body["is_base"] is False


async def test_create_category_with_color(client):
    """POST respects a custom color."""
    cat = MagicMock()
    cat.id = 11
    cat.name = "Sports"
    cat.name_es = "Deportes"
    cat.is_base = False
    cat.color = "#ef4444"

    with patch("finlytics.api.categories.get_or_create_category", new_callable=AsyncMock) as mock:
        mock.return_value = cat
        resp = await client.post("/api/categories", json={"name": "Sports", "color": "#ef4444"})

    assert resp.status_code == 201
    assert resp.json()["color"] == "#ef4444"


async def test_create_category_idempotent(client):
    """POST returns 201 even when category already exists (idempotent)."""
    cat = MagicMock()
    cat.id = 1
    cat.name = "Groceries"
    cat.name_es = "Compras"
    cat.is_base = True
    cat.color = "#22c55e"

    with patch("finlytics.api.categories.get_or_create_category", new_callable=AsyncMock) as mock:
        mock.return_value = cat
        resp = await client.post("/api/categories", json={"name": "Groceries"})

    assert resp.status_code == 201
    assert resp.json()["id"] == 1


async def test_create_category_schema_fields(client):
    """POST response contains all CategoryOut fields."""
    cat = MagicMock()
    cat.id = 12
    cat.name = "Beauty"
    cat.name_es = None
    cat.is_base = False
    cat.color = "#64748b"

    with patch("finlytics.api.categories.get_or_create_category", new_callable=AsyncMock) as mock:
        mock.return_value = cat
        resp = await client.post("/api/categories", json={"name": "Beauty"})

    assert set(resp.json().keys()) == {"id", "name", "is_base", "color", "name_es", "tx_count"}
    assert resp.json()["name_es"] is None
    assert resp.json()["tx_count"] == 0


# ── translate-on-create edge cases ───────────────────────────────────────────

async def test_canonical_english_normalization(client, mock_session):
    """translate result → stored name is canonical English, not the raw input.

    Monkeypatches ``finlytics.db.repository.translate_category_name`` so the
    full ``get_or_create_category`` path runs.  POST "Ropa" must store
    name="Clothing" (canonical) and name_es="Ropa".
    """
    from unittest.mock import MagicMock as _MagicMock
    exec_result = _MagicMock()
    exec_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = exec_result

    def _assign_id(obj):
        obj.id = 99
        if obj.color is None:
            obj.color = "#64748b"

    mock_session.add.side_effect = _assign_id

    with patch("finlytics.db.repository.translate_category_name", new_callable=AsyncMock) as mock_t:
        mock_t.return_value = {"name_en": "Clothing", "name_es": "Ropa"}
        resp = await client.post("/api/categories", json={"name": "Ropa"})
        mock_t.assert_called_once_with("Ropa")

    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Clothing"
    assert body["name_es"] == "Ropa"


async def test_dedup_same_canonical_name(client, mock_session):
    """Second creation resolving to the same canonical English name returns the existing row.

    "Clothing" and "Ropa" both translate to name_en="Clothing" — no duplicate INSERT.
    """
    from unittest.mock import MagicMock as _MagicMock
    existing = _MagicMock()
    existing.id = 5
    existing.name = "Clothing"
    existing.name_es = "Ropa"
    existing.is_base = False
    existing.color = "#64748b"

    exec_result = _MagicMock()
    exec_result.scalar_one_or_none.return_value = existing
    mock_session.execute.return_value = exec_result

    with patch("finlytics.db.repository.translate_category_name", new_callable=AsyncMock) as mock_t:
        mock_t.return_value = {"name_en": "Clothing", "name_es": "Ropa"}
        resp = await client.post("/api/categories", json={"name": "Clothing"})

    assert resp.status_code == 201
    body = resp.json()
    assert body["id"] == 5
    assert body["name"] == "Clothing"
    mock_session.add.assert_not_called()


async def test_translate_none_graceful_fallback(client, mock_session):
    """translate returning None → literal name stored, name_es null, 201 with no error.

    Simulates LLM unconfigured / network failure: the endpoint must succeed
    with the raw input as the category name and name_es=null.
    """
    from unittest.mock import MagicMock as _MagicMock
    exec_result = _MagicMock()
    exec_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = exec_result

    def _assign_id(obj):
        obj.id = 42
        if obj.color is None:
            obj.color = "#64748b"

    mock_session.add.side_effect = _assign_id

    with patch("finlytics.db.repository.translate_category_name", new_callable=AsyncMock) as mock_t:
        mock_t.return_value = None
        resp = await client.post("/api/categories", json={"name": "Mascotas"})

    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Mascotas"
    assert body["name_es"] is None


# ── tx_count propagation ──────────────────────────────────────────────────────

async def test_list_categories_tx_count_values(client):
    """tx_count from the query layer is preserved verbatim in GET /api/categories."""
    with patch("finlytics.db.queries.get_categories", new_callable=AsyncMock) as mock:
        mock.return_value = [
            {"id": 1, "name": "Groceries", "is_base": True, "color": "#22c55e",
             "name_es": "Compras", "tx_count": 7},
            {"id": 2, "name": "Unused", "is_base": False, "color": "#64748b",
             "name_es": None, "tx_count": 0},
        ]
        resp = await client.get("/api/categories")

    data = resp.json()
    assert data[0]["tx_count"] == 7
    assert data[1]["tx_count"] == 0
