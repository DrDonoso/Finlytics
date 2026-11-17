"""What's new: which notes about Finlytics' changes the user has already read.

GET  /api/whats-new        — the ids read so far (``null`` until the interface records any).
POST /api/whats-new/seen   — add ids to the notes read.

The notes ship with the interface (``frontend/src/whatsNew/notes/``, one JSON file per note named
``YYYY-MM-DD-slug``) and the server never reads them: it only keeps the ids the user has read
(``users.whats_new_seen``).  NULL means the interface never recorded any, as for a new user: it then
marks every current note as read without showing them, so only later changes are announced.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from finlytics.api.deps import get_current_user, get_db
from finlytics.db.models import User

router = APIRouter(prefix="/whats-new", tags=["whats-new"])

# The newest ids kept per user: far more notes than will ever ship, and a bound on what a client
# can make the server store.
MAX_SEEN = 1000

# A note's id is its file name in frontend/src/whatsNew/notes/: ``YYYY-MM-DD-slug``.
NOTE_ID_PATTERN = r"^\d{4}-\d{2}-\d{2}-[a-z0-9]+(-[a-z0-9]+)*$"
NoteId = Annotated[str, Field(max_length=80, pattern=NOTE_ID_PATTERN)]


class WhatsNewOut(BaseModel):
    # Notes the user has read (sorted); null until the interface records them for the first time.
    seen: list[str] | None


class WhatsNewSeenIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ids: Annotated[list[NoteId], Field(min_length=1, max_length=500)]


def _seen_out(seen: object) -> WhatsNewOut:
    return WhatsNewOut(seen=seen if isinstance(seen, list) else None)


@router.get("", response_model=WhatsNewOut)
async def get_whats_new(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WhatsNewOut:
    return _seen_out(await db.scalar(select(User.whats_new_seen).where(User.id == user.id)))


@router.post("/seen", response_model=WhatsNewOut)
async def mark_seen(
    body: WhatsNewSeenIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WhatsNewOut:
    """Add ``ids`` to the notes the user has read (ids already there change nothing)."""
    # Locked (FOR NO KEY UPDATE on PostgreSQL) so that two tabs saving at once both add theirs.
    account = await db.scalar(
        select(User)
        .where(User.id == user.id)
        .with_for_update(key_share=True)
        .execution_options(populate_existing=True)
    )
    if account is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    read = account.whats_new_seen if isinstance(account.whats_new_seen, list) else []
    # Ids start with their date: sorted, the newest are the last.
    account.whats_new_seen = sorted({*read, *body.ids})[-MAX_SEEN:]
    await db.commit()
    return _seen_out(account.whats_new_seen)
