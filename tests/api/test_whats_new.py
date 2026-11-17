"""What's new: the notes the signed-in user has read (``/api/whats-new``), merged, capped and
format-checked. The row lock needs PostgreSQL and is covered in ``tests/pg``."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from finlytics.api import whats_new
from finlytics.api.deps import get_current_user, get_db
from finlytics.app import app
from finlytics.db.models import Base, User

SEEN = "/api/whats-new/seen"
LAUNCH = "2026-11-17-novedades"


@pytest.fixture
async def factory():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        s.add(User(id=1, username="demo", password_hash="x", created_at=datetime.now(UTC)))
        await s.commit()
    yield maker
    await engine.dispose()


@pytest.fixture
async def api(factory):
    async def _get_db():
        async with factory() as s:
            yield s

    async def _current_user():
        async with factory() as s:
            return await s.get(User, 1)

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_current_user] = _current_user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)


async def stored(factory) -> object:
    async with factory() as s:
        return await s.scalar(select(User.whats_new_seen).where(User.id == 1))


async def test_needs_a_session() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        assert (await c.get("/api/whats-new")).status_code == 401
        assert (await c.post(SEEN, json={"ids": [LAUNCH]})).status_code == 401


async def test_nothing_recorded_until_the_first_post_then_notes_add_up(api, factory) -> None:
    assert (await api.get("/api/whats-new")).json() == {"seen": None}
    assert (await api.post(SEEN, json={"ids": [LAUNCH]})).json() == {"seen": [LAUNCH]}
    later, earlier = "2027-02-03-albums", "2026-12-01-zoom"
    response = await api.post(SEEN, json={"ids": [later, LAUNCH, earlier, later]})
    assert response.json() == {"seen": [LAUNCH, earlier, later]}
    assert (await api.get("/api/whats-new")).json() == {"seen": [LAUNCH, earlier, later]}
    assert await stored(factory) == [LAUNCH, earlier, later]


async def test_only_the_newest_notes_are_kept(api, monkeypatch) -> None:
    monkeypatch.setattr(whats_new, "MAX_SEEN", 3)
    await api.post(SEEN, json={"ids": ["2026-01-01-a", "2026-02-01-b", "2026-03-01-c"]})
    response = await api.post(SEEN, json={"ids": ["2026-04-01-d", "2025-12-31-z"]})
    assert response.json() == {"seen": ["2026-02-01-b", "2026-03-01-c", "2026-04-01-d"]}


@pytest.mark.parametrize(
    "body",
    [
        {"ids": []},
        {"ids": [f"2026-01-01-n{index}" for index in range(501)]},
        {"ids": "2026-11-17-novedades"},
        {"ids": [7]},
        {"ids": ["novedades"]},
        {"ids": ["2026-11-17-Novedades"]},
        {"ids": ["2026-11-17-" + "a" * 80]},
        {"ids": [LAUNCH], "extra": 1},
        {},
    ],
)
async def test_malformed_requests_are_rejected_and_store_nothing(api, factory, body) -> None:
    assert (await api.post(SEEN, json=body)).status_code == 422
    assert await stored(factory) is None
