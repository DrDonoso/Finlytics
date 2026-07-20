"""Orchestrator unit tests: idempotency + auto-resolve.

Uses an in-memory SQLite database (aiosqlite) so these tests are self-contained
and do not require a running PostgreSQL instance.

Coverage:
  - evaluate_notifications inserts a new row for each DetectedNotification
  - Running twice (same detected set) does NOT create duplicate rows
  - A notification whose dedup_key disappears from the detected set gets resolved_at set
  - A dismissed notification is NOT auto-resolved (dismissed_at acts as a shield)
  - A resolved notification re-activates (resolved_at cleared) when the key re-appears
  - read_at and dismissed_at survive upsert (user state is preserved)
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from finlytics.db.models import Base, Notification
from finlytics.notifications.detectors import DetectedNotification
from finlytics.notifications.service import evaluate_notifications

# ── In-memory SQLite fixtures ─────────────────────────────────────────────────

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

_WARNING = DetectedNotification(
    source="test",
    type="test_condition",
    severity="warning",
    dedup_key="test:condition:2026-06",
    title_key="notif.test",
    title_args={"foo": "bar"},
    action_link="/test",
)

_WARNING_2 = DetectedNotification(
    source="test",
    type="test_condition",
    severity="warning",
    dedup_key="test:condition:2026-07",
    title_key="notif.test",
    title_args={"foo": "baz"},
    action_link="/test",
)


@pytest.fixture
async def db():
    engine = create_async_engine(TEST_DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


def _mock_registry(detected: list[DetectedNotification]):
    """Return a mock REGISTRY list with a single detector producing *detected*."""
    detector = AsyncMock()
    detector.id = "test"
    detector.is_condition = True
    detector.evaluate = AsyncMock(return_value=detected)
    return [detector]


# ── Tests ─────────────────────────────────────────────────────────────────────

async def test_new_notification_inserted(db: AsyncSession, monkeypatch):
    """A fresh detected notification creates exactly one row."""
    monkeypatch.setattr(
        "finlytics.notifications.service.REGISTRY",
        _mock_registry([_WARNING]),
    )

    new = await evaluate_notifications(db, user_id=1, today=date(2026, 7, 17))
    assert len(new) == 1
    assert new[0].dedup_key == _WARNING.dedup_key
    assert new[0].source == "test"
    assert new[0].read_at is None
    assert new[0].dismissed_at is None
    assert new[0].resolved_at is None

    rows = (await db.execute(select(Notification))).scalars().all()
    assert len(rows) == 1


async def test_idempotency_no_duplicates(db: AsyncSession, monkeypatch):
    """Calling evaluate_notifications twice with the same output inserts only one row."""
    registry = _mock_registry([_WARNING])
    monkeypatch.setattr("finlytics.notifications.service.REGISTRY", registry)

    first = await evaluate_notifications(db, user_id=1, today=date(2026, 7, 17))
    assert len(first) == 1

    second = await evaluate_notifications(db, user_id=1, today=date(2026, 7, 17))
    assert len(second) == 0  # no new rows on second run

    rows = (await db.execute(select(Notification))).scalars().all()
    assert len(rows) == 1  # still exactly one row


async def test_auto_resolve_when_condition_clears(db: AsyncSession, monkeypatch):
    """When a condition disappears, its row gets resolved_at set."""
    # First run: condition present
    monkeypatch.setattr(
        "finlytics.notifications.service.REGISTRY",
        _mock_registry([_WARNING]),
    )
    await evaluate_notifications(db, user_id=1, today=date(2026, 7, 17))

    # Second run: condition gone
    monkeypatch.setattr(
        "finlytics.notifications.service.REGISTRY",
        _mock_registry([]),
    )
    await evaluate_notifications(db, user_id=1, today=date(2026, 7, 17))

    rows = (await db.execute(select(Notification))).scalars().all()
    assert len(rows) == 1
    assert rows[0].resolved_at is not None


async def test_dismissed_notification_not_auto_resolved(db: AsyncSession, monkeypatch):
    """A dismissed notification is excluded from auto-resolve (dismissed_at is a shield)."""
    registry = _mock_registry([_WARNING])
    monkeypatch.setattr("finlytics.notifications.service.REGISTRY", registry)
    await evaluate_notifications(db, user_id=1, today=date(2026, 7, 17))

    # Simulate user dismissing the notification.
    # Use autobegin: set field on the object then commit (no extra db.begin()).
    rows = (await db.execute(select(Notification))).scalars().all()
    rows[0].dismissed_at = datetime.now(timezone.utc)
    await db.commit()  # commit the dismissed_at update via autobegin

    # Second run: condition gone, but row was dismissed → should NOT be resolved
    monkeypatch.setattr(
        "finlytics.notifications.service.REGISTRY",
        _mock_registry([]),
    )
    await evaluate_notifications(db, user_id=1, today=date(2026, 7, 17))

    rows = (await db.execute(select(Notification))).scalars().all()
    assert rows[0].resolved_at is None  # dismissed: auto-resolve skipped


async def test_reactivation_clears_resolved_at(db: AsyncSession, monkeypatch):
    """A previously resolved notification gets resolved_at cleared when it re-appears."""
    # Run 1: condition present
    monkeypatch.setattr(
        "finlytics.notifications.service.REGISTRY",
        _mock_registry([_WARNING]),
    )
    await evaluate_notifications(db, user_id=1, today=date(2026, 7, 17))

    # Run 2: condition gone → resolved
    monkeypatch.setattr(
        "finlytics.notifications.service.REGISTRY",
        _mock_registry([]),
    )
    await evaluate_notifications(db, user_id=1, today=date(2026, 7, 17))

    rows = (await db.execute(select(Notification))).scalars().all()
    assert rows[0].resolved_at is not None
    # Reset the autobegin transaction started by the SELECT above before Run 3.
    await db.rollback()

    # Run 3: condition re-appears → resolved_at should be cleared
    monkeypatch.setattr(
        "finlytics.notifications.service.REGISTRY",
        _mock_registry([_WARNING]),
    )
    new = await evaluate_notifications(db, user_id=1, today=date(2026, 7, 17))
    assert new == []  # row already existed; not "new"

    rows = (await db.execute(select(Notification))).scalars().all()
    assert rows[0].resolved_at is None  # re-activated


async def test_user_read_state_survives_upsert(db: AsyncSession, monkeypatch):
    """read_at is NOT cleared when the same notification is upserted."""
    monkeypatch.setattr(
        "finlytics.notifications.service.REGISTRY",
        _mock_registry([_WARNING]),
    )
    await evaluate_notifications(db, user_id=1, today=date(2026, 7, 17))

    # Simulate user reading the notification
    read_time = datetime.now(timezone.utc)
    async with db.begin():
        row = (await db.execute(select(Notification))).scalar_one()
        row.read_at = read_time

    # Re-evaluate: condition still present → upsert → read_at must survive
    await evaluate_notifications(db, user_id=1, today=date(2026, 7, 17))

    row = (await db.execute(select(Notification))).scalar_one()
    assert row.read_at == read_time  # unchanged


async def test_multiple_notifications_inserted(db: AsyncSession, monkeypatch):
    """Two different dedup_keys produce two rows."""
    monkeypatch.setattr(
        "finlytics.notifications.service.REGISTRY",
        _mock_registry([_WARNING, _WARNING_2]),
    )
    new = await evaluate_notifications(db, user_id=1, today=date(2026, 7, 17))
    assert len(new) == 2

    rows = (await db.execute(select(Notification))).scalars().all()
    assert len(rows) == 2
    keys = {r.dedup_key for r in rows}
    assert keys == {_WARNING.dedup_key, _WARNING_2.dedup_key}


async def test_different_users_are_isolated(db: AsyncSession, monkeypatch):
    """Notifications for user 1 don't affect user 2 and vice-versa."""
    registry = _mock_registry([_WARNING])
    monkeypatch.setattr("finlytics.notifications.service.REGISTRY", registry)

    await evaluate_notifications(db, user_id=1, today=date(2026, 7, 17))
    await evaluate_notifications(db, user_id=2, today=date(2026, 7, 17))

    u1 = (
        await db.execute(select(Notification).where(Notification.user_id == 1))
    ).scalars().all()
    u2 = (
        await db.execute(select(Notification).where(Notification.user_id == 2))
    ).scalars().all()
    assert len(u1) == 1
    assert len(u2) == 1
    # Reset the autobegin transaction started by the SELECTs above.
    await db.rollback()

    # Auto-resolve for user 2 should NOT affect user 1's row
    monkeypatch.setattr(
        "finlytics.notifications.service.REGISTRY",
        _mock_registry([]),
    )
    await evaluate_notifications(db, user_id=2, today=date(2026, 7, 17))

    u1_after = (
        await db.execute(select(Notification).where(Notification.user_id == 1))
    ).scalars().all()
    assert u1_after[0].resolved_at is None  # user 1 unaffected
