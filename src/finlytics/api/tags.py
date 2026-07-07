"""Tags endpoints: GET (list), POST (create), PATCH (update), DELETE."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from finlytics.api.deps import get_db
from finlytics.api.schemas import TagCreate, TagOut, TagUpdate
from finlytics.db import queries
from finlytics.db.queries import TagNameConflictError

router = APIRouter(prefix="/tags", tags=["tags"])


@router.get("", response_model=list[TagOut])
async def list_tags(session: AsyncSession = Depends(get_db)) -> list[TagOut]:
    """Return all tags sorted alphabetically."""
    return await queries.get_tags(session)


@router.post("", response_model=TagOut, status_code=201)
async def create_tag(
    body: TagCreate,
    session: AsyncSession = Depends(get_db),
) -> TagOut:
    """Create a new tag.

    * 201 — tag created.
    * 409 — a tag with the same (normalised) name already exists.

    ``color`` is optional; omit it to use the default slate-grey (#64748b).
    ``emoji`` is optional; omit it to leave the emoji field empty.
    """
    try:
        tag = await queries.create_tag(
            session, name=body.name, color=body.color, emoji=body.emoji
        )
    except TagNameConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return tag


@router.patch("/{tag_id}", response_model=TagOut)
async def update_tag(
    tag_id: int,
    body: TagUpdate,
    session: AsyncSession = Depends(get_db),
) -> TagOut:
    """Rename, recolour, and/or update the emoji of a tag.

    * 200 — updated.
    * 404 — tag not found.
    * 409 — renaming to a name already held by a different tag.

    ``emoji`` field semantics:
    - Omit the field entirely → emoji unchanged.
    - Send ``null`` → emoji cleared (set to NULL).
    - Send a non-empty string → emoji set to that value.
    """
    extra: dict[str, Any] = {}
    if "emoji" in body.model_fields_set:
        # Explicitly provided (even as null) → pass through to query layer.
        extra["emoji"] = body.emoji

    try:
        tag = await queries.update_tag(
            session, tag_id, name=body.name, color=body.color, **extra
        )
    except TagNameConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    if tag is None:
        raise HTTPException(status_code=404, detail="Tag not found.")
    return tag


@router.delete("/{tag_id}", status_code=204)
async def delete_tag(
    tag_id: int,
    session: AsyncSession = Depends(get_db),
) -> None:
    """Delete a tag and all its transaction links.

    * 204 — deleted.
    * 404 — tag not found.
    """
    deleted = await queries.delete_tag(session, tag_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Tag not found.")
