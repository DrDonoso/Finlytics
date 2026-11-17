"""What's new: two requests saving at once must both land, which needs the row lock."""

from __future__ import annotations

import asyncio

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from finlytics.api.deps import get_current_user, get_db
from finlytics.app import app
from finlytics.db.models import User


async def test_concurrent_saves_keep_every_note(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions() as s, s.begin():
        s.add(User(username="ana", password_hash="x"))

    async def _get_db():
        async with sessions() as s:
            yield s

    async def _current_user():
        async with sessions() as s:
            return await s.scalar(select(User))

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_current_user] = _current_user
    try:
        ids = [f"2026-01-{day:02d}-note" for day in range(1, 21)]
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            responses = await asyncio.gather(
                *(c.post("/api/whats-new/seen", json={"ids": [i]}) for i in ids)
            )
        assert {r.status_code for r in responses} == {200}
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)

    async with sessions() as s:
        assert await s.scalar(select(User.whats_new_seen)) == ids
