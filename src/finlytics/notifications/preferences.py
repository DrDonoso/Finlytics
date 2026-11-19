"""Which alert types leave the app, by push or Telegram, for each user.

A type is a detector's ``id`` (``detectors.REGISTRY``), and every type is on until
the user turns it off. The in-app bell is not affected: it lists every alert.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from finlytics.db.models import NotificationPreference
from finlytics.notifications import detectors


def alert_types() -> list[str]:
    return [detector.id for detector in detectors.REGISTRY]


async def muted_sources(db: AsyncSession, user_id: int) -> set[str]:
    rows = await db.scalars(
        select(NotificationPreference.source).where(
            NotificationPreference.user_id == user_id,
            NotificationPreference.enabled.is_(False),
        )
    )
    return set(rows)


async def get_preferences(db: AsyncSession, user_id: int) -> list[tuple[str, bool]]:
    """Every alert type, in the registry's order, with whether it is sent."""
    muted = await muted_sources(db, user_id)
    return [(source, source not in muted) for source in alert_types()]


async def set_preference(db: AsyncSession, user_id: int, source: str, enabled: bool) -> None:
    """Record the choice; no commit. The caller checks ``source`` against ``alert_types``."""
    row = await db.get(NotificationPreference, (user_id, source))
    if row is None:
        db.add(NotificationPreference(user_id=user_id, source=source, enabled=enabled))
    else:
        row.enabled = enabled
