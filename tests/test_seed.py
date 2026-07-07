"""Tests for seed.py — category color backfill.

Verifies:
* A base category at default grey gets its palette color on re-seed.
* A category with a user-customised color is left untouched.
* A fresh install (categories absent) inserts with the correct palette color.
* No Tag objects are ever inserted by seed (tags are user-created only).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from finlytics.extraction.taxonomy import BASE_CATEGORIES
from seed import BASE_CATEGORY_COLORS, seed

_DEFAULT_GREY = "#64748b"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_result(obj) -> MagicMock:
    """Return a mock execute-result whose scalar_one_or_none() yields obj."""
    r = MagicMock()
    r.scalar_one_or_none.return_value = obj
    return r


def _build_session_and_factory(
    cat_objects: list | None = None,
):
    """Wire up a mock session + async_session_factory.

    cat_objects: len(BASE_CATEGORIES) list; each item is a Category mock or None.
                 None → category does not exist yet (will be inserted).
                 If omitted, all categories are treated as existing with a non-grey color.
    """
    if cat_objects is None:
        cat_objects = [MagicMock(color="already_set") for _ in BASE_CATEGORIES]

    cat_results = [_make_result(obj) for obj in cat_objects]

    mock_session = MagicMock()
    mock_session.execute = AsyncMock(side_effect=cat_results)
    mock_session.add = MagicMock()
    mock_session.begin = MagicMock(return_value=AsyncMock())

    sf_cm = AsyncMock()
    sf_cm.__aenter__ = AsyncMock(return_value=mock_session)
    sf_cm.__aexit__ = AsyncMock(return_value=None)

    return mock_session, sf_cm


# ── Category color backfill tests ─────────────────────────────────────────────

async def test_grey_category_is_backfilled_to_palette_color() -> None:
    """A base category at default grey gets its palette color on re-seed."""
    groceries_cat = MagicMock()
    groceries_cat.color = _DEFAULT_GREY

    # "Groceries" is first in BASE_CATEGORIES (index 0)
    cat_objects = [groceries_cat] + [
        MagicMock(color="already_set") for _ in BASE_CATEGORIES[1:]
    ]
    _, sf_cm = _build_session_and_factory(cat_objects=cat_objects)

    with patch("seed.async_session_factory", return_value=sf_cm):
        await seed()

    expected_color = BASE_CATEGORY_COLORS["Groceries"]
    assert groceries_cat.color == expected_color
    assert groceries_cat.color != _DEFAULT_GREY


async def test_custom_category_color_is_not_overwritten() -> None:
    """A category with a user-customised color must not be touched."""
    dining_cat = MagicMock()
    dining_cat.color = "#abcdef"  # user changed it

    # "Dining" is second in BASE_CATEGORIES (index 1)
    cat_objects = (
        [MagicMock(color="already_set")]
        + [dining_cat]
        + [MagicMock(color="already_set") for _ in BASE_CATEGORIES[2:]]
    )
    _, sf_cm = _build_session_and_factory(cat_objects=cat_objects)

    with patch("seed.async_session_factory", return_value=sf_cm):
        await seed()

    assert dining_cat.color == "#abcdef"


async def test_fresh_install_category_inserts_with_palette_color() -> None:
    """On a fresh install, each base category is inserted with its palette color."""
    cat_objects = [None] * len(BASE_CATEGORIES)
    mock_session, sf_cm = _build_session_and_factory(cat_objects=cat_objects)

    with patch("seed.async_session_factory", return_value=sf_cm):
        await seed()

    from finlytics.db.models import Category
    added_cats = {
        obj.name: obj.color
        for call in mock_session.add.call_args_list
        if isinstance((obj := call.args[0]), Category)
    }
    for name, expected_color in BASE_CATEGORY_COLORS.items():
        assert name in added_cats, f"Category '{name}' was not inserted"
        assert added_cats[name] == expected_color, (
            f"Expected {expected_color!r} for {name!r}, got {added_cats[name]!r}"
        )


async def test_no_tags_seeded() -> None:
    """seed() must not insert any Tag objects — tags are user-created only."""
    cat_objects = [None] * len(BASE_CATEGORIES)
    mock_session, sf_cm = _build_session_and_factory(cat_objects=cat_objects)

    with patch("seed.async_session_factory", return_value=sf_cm):
        await seed()

    from finlytics.db.models import Tag
    added_tags = [
        call.args[0]
        for call in mock_session.add.call_args_list
        if isinstance(call.args[0], Tag)
    ]
    assert added_tags == [], "seed() must not insert any Tag objects"
