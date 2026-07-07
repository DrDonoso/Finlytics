"""Tests for /api/tags — GET, POST, PATCH, DELETE."""

from unittest.mock import AsyncMock, patch

from finlytics.db.models import Tag
from finlytics.db.queries import TagNameConflictError, update_tag


_TAGS = [
    {"id": 1, "name": "agua",     "color": "#3b82f6", "emoji": None, "tx_count": 0},
    {"id": 2, "name": "gas",      "color": "#f97316", "emoji": None, "tx_count": 2},
    {"id": 3, "name": "internet", "color": "#8b5cf6", "emoji": None, "tx_count": 1},
    {"id": 4, "name": "luz",      "color": "#eab308", "emoji": "💡",  "tx_count": 4},
    {"id": 5, "name": "teléfono", "color": "#10b981", "emoji": None, "tx_count": 0},
]


# ── GET /api/tags ─────────────────────────────────────────────────────────────

async def test_list_tags_returns_list(client):
    with patch("finlytics.db.queries.get_tags", new_callable=AsyncMock) as mock:
        mock.return_value = _TAGS
        resp = await client.get("/api/tags")

    assert resp.status_code == 200
    assert len(resp.json()) == 5


async def test_list_tags_empty(client):
    with patch("finlytics.db.queries.get_tags", new_callable=AsyncMock) as mock:
        mock.return_value = []
        resp = await client.get("/api/tags")

    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_tags_schema_fields(client):
    """Each tag item has the expected fields including tx_count."""
    with patch("finlytics.db.queries.get_tags", new_callable=AsyncMock) as mock:
        mock.return_value = [_TAGS[0]]
        resp = await client.get("/api/tags")

    item = resp.json()[0]
    assert set(item.keys()) == {"id", "name", "color", "emoji", "tx_count"}
    assert isinstance(item["id"], int)
    assert isinstance(item["name"], str)
    assert isinstance(item["color"], str)
    assert item["color"].startswith("#")
    assert item["emoji"] is None  # agua has no emoji


async def test_list_tags_emoji_field_present(client):
    """Tags with an emoji expose it in the response."""
    with patch("finlytics.db.queries.get_tags", new_callable=AsyncMock) as mock:
        mock.return_value = [_TAGS[3]]   # luz → emoji "💡"
        resp = await client.get("/api/tags")

    item = resp.json()[0]
    assert item["emoji"] == "💡"
    assert item["name"] == "luz"  # name is clean (no leading emoji)


async def test_list_tags_alphabetical(client):
    """Tags are served in alphabetical order (enforced by the query layer)."""
    with patch("finlytics.db.queries.get_tags", new_callable=AsyncMock) as mock:
        mock.return_value = _TAGS
        resp = await client.get("/api/tags")

    names = [t["name"] for t in resp.json()]
    assert names == sorted(names)


async def test_list_tags_seed_names(client):
    """The five seed tags are present in the canonical (lowercase) form."""
    with patch("finlytics.db.queries.get_tags", new_callable=AsyncMock) as mock:
        mock.return_value = _TAGS
        resp = await client.get("/api/tags")

    names = {t["name"] for t in resp.json()}
    for expected in ("agua", "gas", "internet", "luz", "teléfono"):
        assert expected in names


async def test_list_tags_color_values(client):
    """Each tag carries a non-empty hex colour string."""
    with patch("finlytics.db.queries.get_tags", new_callable=AsyncMock) as mock:
        mock.return_value = _TAGS
        resp = await client.get("/api/tags")

    for item in resp.json():
        assert len(item["color"]) == 7, f"Expected 7-char hex, got {item['color']!r}"
        assert item["color"][0] == "#"


# ── POST /api/tags ────────────────────────────────────────────────────────────

async def test_create_tag_201(client):
    new_tag = {"id": 10, "name": "comida", "color": "#64748b", "emoji": None}
    with patch("finlytics.db.queries.create_tag", new_callable=AsyncMock) as mock:
        mock.return_value = new_tag
        resp = await client.post("/api/tags", json={"name": "Comida"})

    assert resp.status_code == 201
    assert resp.json()["name"] == "comida"
    assert resp.json()["color"] == "#64748b"
    assert resp.json()["emoji"] is None


async def test_create_tag_with_color(client):
    new_tag = {"id": 11, "name": "ocio", "color": "#ef4444", "emoji": None}
    with patch("finlytics.db.queries.create_tag", new_callable=AsyncMock) as mock:
        mock.return_value = new_tag
        resp = await client.post("/api/tags", json={"name": "ocio", "color": "#ef4444"})

    assert resp.status_code == 201
    assert resp.json()["color"] == "#ef4444"


async def test_create_tag_with_emoji(client):
    """POST body can include an emoji."""
    new_tag = {"id": 12, "name": "electricidad", "color": "#eab308", "emoji": "⚡"}
    with patch("finlytics.db.queries.create_tag", new_callable=AsyncMock) as mock:
        mock.return_value = new_tag
        resp = await client.post(
            "/api/tags", json={"name": "electricidad", "emoji": "⚡"}
        )

    assert resp.status_code == 201
    assert resp.json()["emoji"] == "⚡"
    assert resp.json()["name"] == "electricidad"


async def test_create_tag_409_conflict(client):
    with patch("finlytics.db.queries.create_tag", new_callable=AsyncMock) as mock:
        mock.side_effect = TagNameConflictError("Tag 'luz' already exists.")
        resp = await client.post("/api/tags", json={"name": "luz"})

    assert resp.status_code == 409
    assert "already exists" in resp.json()["detail"]


async def test_create_tag_schema_fields(client):
    tag = {"id": 13, "name": "viajes", "color": "#06b6d4", "emoji": None, "tx_count": 0}
    with patch("finlytics.db.queries.create_tag", new_callable=AsyncMock) as mock:
        mock.return_value = tag
        resp = await client.post("/api/tags", json={"name": "viajes"})

    assert set(resp.json().keys()) == {"id", "name", "color", "emoji", "tx_count"}


# ── PATCH /api/tags/{id} ──────────────────────────────────────────────────────

async def test_patch_tag_rename(client):
    updated = {"id": 4, "name": "electricidad", "color": "#eab308", "emoji": "💡"}
    with patch("finlytics.db.queries.update_tag", new_callable=AsyncMock) as mock:
        mock.return_value = updated
        resp = await client.patch("/api/tags/4", json={"name": "electricidad"})

    assert resp.status_code == 200
    assert resp.json()["name"] == "electricidad"


async def test_patch_tag_recolor(client):
    updated = {"id": 4, "name": "luz", "color": "#ff0000", "emoji": "💡"}
    with patch("finlytics.db.queries.update_tag", new_callable=AsyncMock) as mock:
        mock.return_value = updated
        resp = await client.patch("/api/tags/4", json={"color": "#ff0000"})

    assert resp.status_code == 200
    assert resp.json()["color"] == "#ff0000"


async def test_patch_tag_rename_and_recolor(client):
    updated = {"id": 4, "name": "electricidad", "color": "#ff0000", "emoji": None}
    with patch("finlytics.db.queries.update_tag", new_callable=AsyncMock) as mock:
        mock.return_value = updated
        resp = await client.patch(
            "/api/tags/4", json={"name": "electricidad", "color": "#ff0000"}
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "electricidad"
    assert body["color"] == "#ff0000"


async def test_patch_tag_set_emoji(client):
    """PATCH sets emoji when the field is present."""
    updated = {"id": 4, "name": "luz", "color": "#eab308", "emoji": "💡"}
    with patch("finlytics.db.queries.update_tag", new_callable=AsyncMock) as mock:
        mock.return_value = updated
        resp = await client.patch("/api/tags/4", json={"emoji": "💡"})

    assert resp.status_code == 200
    assert resp.json()["emoji"] == "💡"


async def test_patch_tag_clear_emoji(client):
    """PATCH clears emoji when null is sent explicitly."""
    updated = {"id": 4, "name": "luz", "color": "#eab308", "emoji": None}
    with patch("finlytics.db.queries.update_tag", new_callable=AsyncMock) as mock:
        mock.return_value = updated
        resp = await client.patch("/api/tags/4", json={"emoji": None})

    assert resp.status_code == 200
    assert resp.json()["emoji"] is None


async def test_patch_tag_404(client):
    with patch("finlytics.db.queries.update_tag", new_callable=AsyncMock) as mock:
        mock.return_value = None
        resp = await client.patch("/api/tags/999", json={"name": "x"})

    assert resp.status_code == 404


async def test_patch_tag_409_name_conflict(client):
    with patch("finlytics.db.queries.update_tag", new_callable=AsyncMock) as mock:
        mock.side_effect = TagNameConflictError("Tag 'gas' already exists.")
        resp = await client.patch("/api/tags/4", json={"name": "gas"})

    assert resp.status_code == 409
    assert "already exists" in resp.json()["detail"]


# ── DELETE /api/tags/{id} ─────────────────────────────────────────────────────

async def test_delete_tag_204(client):
    with patch("finlytics.db.queries.delete_tag", new_callable=AsyncMock) as mock:
        mock.return_value = True
        resp = await client.delete("/api/tags/4")

    assert resp.status_code == 204
    assert resp.content == b""


async def test_delete_tag_404(client):
    with patch("finlytics.db.queries.delete_tag", new_callable=AsyncMock) as mock:
        mock.return_value = False
        resp = await client.delete("/api/tags/999")

    assert resp.status_code == 404


# ── tag emoji-split on RENAME ─────────────────────────────────────────────────

async def test_update_tag_leading_emoji_split_on_rename(mock_session):
    """Renaming a tag to '💡 luz' auto-splits the leading emoji: name='luz', emoji='💡'.

    Calls ``update_tag`` directly (bypassing the HTTP layer) to verify that
    ``_split_leading_emoji`` is applied inside the rename path.
    """
    from unittest.mock import MagicMock as _MagicMock
    tag = Tag(id=4, name="electricidad", color="#eab308", emoji=None)
    exec_result = _MagicMock()
    # First execute: lookup tag by id; second: conflict-name check (no conflict)
    exec_result.scalar_one_or_none.side_effect = [tag, None]
    mock_session.execute.return_value = exec_result

    result = await update_tag(mock_session, 4, name="💡 luz")

    assert result is not None
    assert result["name"] == "luz"
    assert result["emoji"] == "💡"


# ── tx_count propagation for tags ─────────────────────────────────────────────

async def test_list_tags_tx_count_values(client):
    """tx_count from the query layer is preserved verbatim in GET /api/tags."""
    with patch("finlytics.db.queries.get_tags", new_callable=AsyncMock) as mock:
        mock.return_value = [
            {"id": 4, "name": "luz",  "color": "#eab308", "emoji": "💡", "tx_count": 4},
            {"id": 1, "name": "agua", "color": "#3b82f6", "emoji": None,  "tx_count": 0},
        ]
        resp = await client.get("/api/tags")

    data = resp.json()
    luz  = next(t for t in data if t["name"] == "luz")
    agua = next(t for t in data if t["name"] == "agua")
    assert luz["tx_count"] == 4
    assert agua["tx_count"] == 0
