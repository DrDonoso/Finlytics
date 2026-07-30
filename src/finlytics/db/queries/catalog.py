"""Consultas sobre categorias y etiquetas.

Van juntas porque comparten proposito: son las dos taxonomias con las que
se clasifica una transaccion.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from finlytics.db.models import Category, Tag, Transaction, transaction_tags

from finlytics.db.queries._filters import (
    _split_leading_emoji,
)


# ── Category queries ──────────────────────────────────────────────────────────

async def get_categories(session: AsyncSession) -> list[dict[str, Any]]:
    stmt = (
        select(
            Category.id,
            Category.name,
            Category.name_es,
            Category.is_base,
            Category.color,
            func.count(Transaction.id).label("tx_count"),
        )
        .select_from(Category)
        .outerjoin(Transaction, Transaction.category_id == Category.id)
        .group_by(Category.id, Category.name, Category.name_es, Category.is_base, Category.color)
        .order_by(Category.name)
    )
    rows = (await session.execute(stmt)).all()
    return [
        {
            "id": r.id,
            "name": r.name,
            "name_es": r.name_es,
            "is_base": r.is_base,
            "color": r.color,
            "tx_count": r.tx_count,
        }
        for r in rows
    ]


async def get_tags(session: AsyncSession) -> list[dict[str, Any]]:
    """Return all tags sorted alphabetically, each with a transaction count."""
    stmt = (
        select(
            Tag.id,
            Tag.name,
            Tag.color,
            Tag.emoji,
            func.count(transaction_tags.c.transaction_id).label("tx_count"),
        )
        .select_from(Tag)
        .outerjoin(transaction_tags, transaction_tags.c.tag_id == Tag.id)
        .group_by(Tag.id, Tag.name, Tag.color, Tag.emoji)
        .order_by(Tag.name)
    )
    rows = (await session.execute(stmt)).all()
    return [
        {"id": r.id, "name": r.name, "color": r.color, "emoji": r.emoji, "tx_count": r.tx_count}
        for r in rows
    ]


class TagNameConflictError(Exception):
    """Raised when creating or renaming a tag would duplicate an existing name."""


async def create_tag(
    session: AsyncSession,
    name: str,
    color: str | None = None,
    emoji: str | None = None,
) -> dict[str, Any]:
    """Create a new tag.  Raises ``TagNameConflictError`` if name already exists.

    Leading emoji is auto-split from *name* (e.g. "💡 luz" → name="luz",
    emoji="💡").  If an explicit *emoji* is supplied it takes precedence and
    only the name part is normalised.

    ``name`` is normalised (strip + lowercase after emoji split) before storage.
    ``color`` defaults to the server_default ("#64748b") when not supplied.
    """
    async with session.begin():
        derived_emoji, name_clean = _split_leading_emoji(name.strip())
        if emoji is None:
            emoji = derived_emoji
        name_norm = name_clean.strip().lower()

        existing = (
            await session.execute(select(Tag).where(Tag.name == name_norm))
        ).scalar_one_or_none()
        if existing is not None:
            raise TagNameConflictError(f"Tag '{name_norm}' already exists.")
        kwargs: dict[str, Any] = {"name": name_norm}
        if color is not None:
            kwargs["color"] = color
        if emoji is not None:
            kwargs["emoji"] = emoji
        tag = Tag(**kwargs)
        session.add(tag)
        await session.flush()
        return {"id": tag.id, "name": tag.name, "color": tag.color, "emoji": tag.emoji}


# Sentinel used internally by update_tag to distinguish "not provided" from "set to null".
_FIELD_UNSET = object()


async def update_tag(
    session: AsyncSession,
    tag_id: int,
    *,
    name: str | None = None,
    color: str | None = None,
    emoji: Any = _FIELD_UNSET,
) -> dict[str, Any] | None:
    """Rename and/or recolour/re-emoji a tag.

    Returns ``None`` if the tag does not exist.
    Raises ``TagNameConflictError`` if renaming to a name already held by a
    *different* tag.

    Leading emoji is auto-split from *name* when no explicit *emoji* is
    provided.  Example: rename to "💡 luz" with no emoji field → stored as
    name="luz", emoji="💡".

    ``emoji`` semantics (use ``model_fields_set`` in the endpoint):
    - not passed (default ``_FIELD_UNSET``) → derive from name if present; no
      change to emoji column when name has no leading emoji
    - passed as ``None`` → clear emoji (set to NULL)
    - passed as ``str``  → set emoji to that value
    """
    async with session.begin():
        tag = (
            await session.execute(select(Tag).where(Tag.id == tag_id))
        ).scalar_one_or_none()
        if tag is None:
            return None

        if name is not None:
            derived_emoji, name_clean = _split_leading_emoji(name.strip())
            name_norm = name_clean.strip().lower()
            # When no explicit emoji was provided, derive it from the name prefix.
            if emoji is _FIELD_UNSET and derived_emoji is not None:
                emoji = derived_emoji
            if name_norm != tag.name:
                conflict = (
                    await session.execute(
                        select(Tag).where(Tag.name == name_norm, Tag.id != tag_id)
                    )
                ).scalar_one_or_none()
                if conflict is not None:
                    raise TagNameConflictError(f"Tag '{name_norm}' already exists.")
                tag.name = name_norm

        if color is not None:
            tag.color = color

        if emoji is not _FIELD_UNSET:
            tag.emoji = emoji  # None → clears column; str → sets value

        await session.flush()
        return {"id": tag.id, "name": tag.name, "color": tag.color, "emoji": tag.emoji}


async def delete_tag(session: AsyncSession, tag_id: int) -> bool:
    """Delete a tag and its transaction_tags links (via CASCADE).

    Returns ``True`` if deleted, ``False`` if the tag does not exist.
    """
    async with session.begin():
        tag = (
            await session.execute(select(Tag).where(Tag.id == tag_id))
        ).scalar_one_or_none()
        if tag is None:
            return False
        await session.delete(tag)
        return True


async def update_category(
    session: AsyncSession,
    category_id: int,
    *,
    color: str | None = None,
) -> dict[str, Any] | None:
    """Update a category's color.

    Returns the updated category dict, or ``None`` if not found.
    Only ``color`` is writable for now (renaming base categories is out of scope).
    """
    async with session.begin():
        cat = (
            await session.execute(select(Category).where(Category.id == category_id))
        ).scalar_one_or_none()
        if cat is None:
            return None
        if color is not None:
            cat.color = color
        await session.flush()
        return {
            "id": cat.id,
            "name": cat.name,
            "name_es": cat.name_es,
            "is_base": cat.is_base,
            "color": cat.color,
        }
