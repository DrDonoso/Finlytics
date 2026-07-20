"""API-level tests for /api/notifications endpoints.

Uses a real in-memory SQLite database (aiosqlite + StaticPool) so that
evaluate_notifications and every endpoint SQL path run against a real engine.
REGISTRY is monkeypatched per-test to control detector output — same pattern
as tests/notifications/test_orchestrator.py.

StaticPool note: all sessions share ONE underlying connection.  To avoid
"connection already checked out" deadlocks, every setup / assertion block uses
*short-lived* sessions (``async with factory() as s: …``).  These are created
and closed sequentially — never concurrently — so the single connection is
always idle when the next session acquires it.

Test areas
──────────
1. GET  /notifications  — active-only filter, severity+recency sort, evaluation trigger
2. GET  /unread-count   — counts only unread-active; does NOT run evaluation
3. POST /read-all       — marks all unread-active; returns correct {updated} count
4. POST /{id}/read      — sets read_at; 204; no-op on already-read; 404 on missing
5. POST /{id}/dismiss   — removes from list; shields row from auto-resolve; 404 on missing
6. Cross-user isolation — list/count isolation; 404 on foreign-user notification
7. Unauthenticated      — all 5 endpoints return 401 without a session cookie
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from finlytics.api.deps import get_current_user, get_db
from finlytics.app import app
from finlytics.db.models import Base, Notification
from finlytics.notifications.detectors import DetectedNotification

USER_ID = 1
OTHER_USER_ID = 2


# ── Registry helpers ──────────────────────────────────────────────────────────


def _null_registry():
    """Empty detector list — no evaluation happens; pre-inserted rows are untouched."""
    return []


def _empty_detector_registry():
    """One detector with id='test' that returns no conditions.

    Triggers the auto-resolve sweep for source='test' rows (any active row
    whose dedup_key is NOT in the (empty) detected set gets resolved_at set).
    Use this when testing auto-resolve behaviour.
    """
    d = AsyncMock()
    d.id = "test"
    d.is_condition = True
    d.evaluate = AsyncMock(return_value=[])
    return [d]


def _registry_with(detected: list[DetectedNotification]):
    """One detector with id='test' that returns the given notifications."""
    d = AsyncMock()
    d.id = "test"
    d.is_condition = True
    d.evaluate = AsyncMock(return_value=detected)
    return [d]


# ── ORM object factory ────────────────────────────────────────────────────────


def _make_notif(
    user_id: int = USER_ID,
    severity: str = "info",
    source: str = "test",
    dedup_key: str | None = None,
    read_at: datetime | None = None,
    dismissed_at: datetime | None = None,
    resolved_at: datetime | None = None,
) -> Notification:
    now = datetime.now(timezone.utc)
    return Notification(
        user_id=user_id,
        source=source,
        type="test_type",
        severity=severity,
        dedup_key=dedup_key or f"test:{severity}:{uuid.uuid4().hex}",
        title_key="notif.test",
        title_args={},
        created_at=now,
        updated_at=now,
        read_at=read_at,
        dismissed_at=dismissed_at,
        resolved_at=resolved_at,
    )


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
async def sqlite_engine():
    """Function-scoped in-memory SQLite engine (StaticPool — single shared connection)."""
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture
async def notif_client(sqlite_engine):
    """ASGI client wired to the in-memory SQLite DB; auth = user_id=1."""
    factory = async_sessionmaker(sqlite_engine, class_=AsyncSession, expire_on_commit=False)

    async def _get_db():
        async with factory() as s:
            yield s

    user = MagicMock()
    user.id = USER_ID

    async def _get_user():
        return user

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_current_user] = _get_user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
async def unauthenticated_client():
    """Only get_db overridden; real get_current_user enforces 401."""
    mock_session = MagicMock()
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.close = AsyncMock()
    begin_cm = AsyncMock()
    mock_session.begin = MagicMock(return_value=begin_cm)

    async def _override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = _override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


def _sf(engine) -> async_sessionmaker:
    """Short alias: return a session factory for *engine*."""
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# =============================================================================
# 1. GET /api/notifications — filter, sort order, evaluation
# =============================================================================


async def test_list_excludes_dismissed_and_resolved(
    sqlite_engine, notif_client, monkeypatch
):
    """Active notifications appear; dismissed and resolved rows are excluded."""
    monkeypatch.setattr("finlytics.notifications.service.REGISTRY", _null_registry())
    factory = _sf(sqlite_engine)

    async with factory() as s:
        active = _make_notif(USER_ID, severity="info")
        dismissed = _make_notif(USER_ID, dismissed_at=datetime.now(timezone.utc))
        resolved = _make_notif(USER_ID, resolved_at=datetime.now(timezone.utc))
        s.add_all([active, dismissed, resolved])
        await s.commit()
        await s.refresh(active)
        active_id = active.id

    resp = await notif_client.get("/api/notifications")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["id"] == active_id
    # resolved_at is intentionally absent from NotificationOut
    assert "resolved_at" not in data[0]


async def test_list_sort_warning_before_info_then_newest_first(
    sqlite_engine, notif_client, monkeypatch
):
    """Warnings appear before infos; within same severity newest row comes first."""
    monkeypatch.setattr("finlytics.notifications.service.REGISTRY", _null_registry())
    factory = _sf(sqlite_engine)
    now = datetime.now(timezone.utc)

    async with factory() as s:
        info_old = _make_notif(USER_ID, severity="info")
        info_old.created_at = now - timedelta(hours=2)

        info_new = _make_notif(USER_ID, severity="info")
        info_new.created_at = now - timedelta(hours=1)

        warn = _make_notif(USER_ID, severity="warning")
        warn.created_at = now - timedelta(minutes=30)

        s.add_all([info_old, info_new, warn])
        await s.commit()
        await s.refresh(info_old)
        await s.refresh(info_new)
        await s.refresh(warn)
        warn_id = warn.id
        info_new_id = info_new.id
        info_old_id = info_old.id

    resp = await notif_client.get("/api/notifications")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 3
    ids = [d["id"] for d in data]
    # Severity ordering: warning before info
    assert data[0]["severity"] == "warning"
    assert ids[0] == warn_id
    # Within info: newest first
    assert ids[1] == info_new_id
    assert ids[2] == info_old_id


async def test_list_response_has_required_fields(
    sqlite_engine, notif_client, monkeypatch
):
    """Every notification in the list carries all NotificationOut fields."""
    monkeypatch.setattr("finlytics.notifications.service.REGISTRY", _null_registry())
    factory = _sf(sqlite_engine)

    async with factory() as s:
        n = _make_notif(USER_ID, source="statement", severity="warning")
        n.body_key = "notif.body"
        n.action_link = "/finances"
        s.add(n)
        await s.commit()

    resp = await notif_client.get("/api/notifications")
    assert resp.status_code == 200
    item = resp.json()[0]
    for field in ("id", "source", "type", "severity", "title_key", "title_args",
                  "body_key", "body_args", "action_link", "created_at",
                  "read_at", "dismissed_at"):
        assert field in item, f"Missing field: {field}"


async def test_list_triggers_evaluation_condition_appears(
    sqlite_engine, notif_client, monkeypatch
):
    """When a condition detector fires, GET /notifications creates the notification row."""
    detected = DetectedNotification(
        source="test",
        type="missing_statement",
        severity="warning",
        dedup_key="test:condition:2026-07",
        title_key="notif.test",
        title_args={"month": "2026-07"},
        action_link="/finances",
    )
    monkeypatch.setattr("finlytics.notifications.service.REGISTRY", _registry_with([detected]))

    resp = await notif_client.get("/api/notifications")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["severity"] == "warning"
    assert data[0]["source"] == "test"
    assert data[0]["title_key"] == "notif.test"
    assert data[0]["title_args"] == {"month": "2026-07"}


async def test_list_auto_resolves_when_condition_clears(
    sqlite_engine, notif_client, monkeypatch
):
    """When a condition disappears, the next GET auto-resolves and hides the row."""
    detected = DetectedNotification(
        source="test",
        type="missing_statement",
        severity="warning",
        dedup_key="test:condition:auto-resolve",
        title_key="notif.test",
        title_args={},
    )
    # Condition present → row created
    monkeypatch.setattr("finlytics.notifications.service.REGISTRY", _registry_with([detected]))
    resp1 = await notif_client.get("/api/notifications")
    assert len(resp1.json()) == 1

    # Condition cleared → row auto-resolved → excluded from list
    monkeypatch.setattr(
        "finlytics.notifications.service.REGISTRY", _empty_detector_registry()
    )
    resp2 = await notif_client.get("/api/notifications")
    assert resp2.status_code == 200
    assert resp2.json() == []


# =============================================================================
# 2. GET /api/notifications/unread-count
# =============================================================================


async def test_unread_count_active_only(sqlite_engine, notif_client, monkeypatch):
    """Count = rows where read_at IS NULL AND dismissed_at IS NULL AND resolved_at IS NULL."""
    monkeypatch.setattr("finlytics.notifications.service.REGISTRY", _null_registry())
    factory = _sf(sqlite_engine)

    async with factory() as s:
        s.add_all([
            _make_notif(USER_ID),                                           # unread active
            _make_notif(USER_ID),                                           # unread active
            _make_notif(USER_ID, read_at=datetime.now(timezone.utc)),      # read — excluded
            _make_notif(USER_ID, dismissed_at=datetime.now(timezone.utc)), # dismissed — excluded
            _make_notif(USER_ID, resolved_at=datetime.now(timezone.utc)),  # resolved — excluded
        ])
        await s.commit()

    resp = await notif_client.get("/api/notifications/unread-count")
    assert resp.status_code == 200
    assert resp.json() == {"count": 2}


async def test_unread_count_decreases_after_read(sqlite_engine, notif_client, monkeypatch):
    """Marking a notification read decreases the unread count."""
    monkeypatch.setattr("finlytics.notifications.service.REGISTRY", _null_registry())
    factory = _sf(sqlite_engine)

    async with factory() as s:
        n = _make_notif(USER_ID)
        s.add(n)
        await s.commit()
        await s.refresh(n)
        notif_id = n.id

    assert (await notif_client.get("/api/notifications/unread-count")).json()["count"] == 1
    await notif_client.post(f"/api/notifications/{notif_id}/read")
    assert (await notif_client.get("/api/notifications/unread-count")).json()["count"] == 0


async def test_unread_count_decreases_after_dismiss(sqlite_engine, notif_client, monkeypatch):
    """Dismissing an unread notification decreases the unread count."""
    monkeypatch.setattr("finlytics.notifications.service.REGISTRY", _null_registry())
    factory = _sf(sqlite_engine)

    async with factory() as s:
        n = _make_notif(USER_ID)
        s.add(n)
        await s.commit()
        await s.refresh(n)
        notif_id = n.id

    assert (await notif_client.get("/api/notifications/unread-count")).json()["count"] == 1
    await notif_client.post(f"/api/notifications/{notif_id}/dismiss")
    assert (await notif_client.get("/api/notifications/unread-count")).json()["count"] == 0


async def test_unread_count_does_not_run_evaluation(
    sqlite_engine, notif_client, monkeypatch
):
    """GET /unread-count must NOT call evaluate_notifications (safe to poll for badge)."""
    monkeypatch.setattr("finlytics.notifications.service.REGISTRY", _null_registry())
    factory = _sf(sqlite_engine)

    async with factory() as s:
        s.add(_make_notif(USER_ID))
        await s.commit()

    eval_mock = AsyncMock(return_value=[])
    with patch("finlytics.api.notifications.evaluate_notifications", eval_mock):
        resp = await notif_client.get("/api/notifications/unread-count")

    assert resp.status_code == 200
    assert resp.json()["count"] == 1
    eval_mock.assert_not_called()


# =============================================================================
# 3. POST /api/notifications/{id}/read
# =============================================================================


async def test_mark_read_sets_read_at_and_returns_204(
    sqlite_engine, notif_client, monkeypatch
):
    """POST /{id}/read returns 204 and sets read_at in the DB."""
    monkeypatch.setattr("finlytics.notifications.service.REGISTRY", _null_registry())
    factory = _sf(sqlite_engine)

    async with factory() as s:
        n = _make_notif(USER_ID)
        s.add(n)
        await s.commit()
        await s.refresh(n)
        notif_id = n.id

    resp = await notif_client.post(f"/api/notifications/{notif_id}/read")
    assert resp.status_code == 204

    async with factory() as s:
        row = (
            await s.execute(select(Notification).where(Notification.id == notif_id))
        ).scalar_one()
        assert row.read_at is not None


async def test_mark_read_already_read_is_noop(sqlite_engine, notif_client, monkeypatch):
    """Calling POST /{id}/read on an already-read notification does not reset read_at."""
    monkeypatch.setattr("finlytics.notifications.service.REGISTRY", _null_registry())
    factory = _sf(sqlite_engine)

    async with factory() as s:
        n = _make_notif(USER_ID)
        s.add(n)
        await s.commit()
        await s.refresh(n)
        notif_id = n.id

    # First read: sets read_at
    await notif_client.post(f"/api/notifications/{notif_id}/read")
    async with factory() as s:
        row = (
            await s.execute(select(Notification).where(Notification.id == notif_id))
        ).scalar_one()
        first_read_at = row.read_at
        assert first_read_at is not None

    # Second read: no-op — read_at must not change
    await notif_client.post(f"/api/notifications/{notif_id}/read")
    async with factory() as s:
        row = (
            await s.execute(select(Notification).where(Notification.id == notif_id))
        ).scalar_one()
        assert row.read_at == first_read_at


async def test_mark_read_404_on_nonexistent(notif_client, monkeypatch):
    """POST /9999/read returns 404 when no such notification exists."""
    monkeypatch.setattr("finlytics.notifications.service.REGISTRY", _null_registry())
    resp = await notif_client.post("/api/notifications/9999/read")
    assert resp.status_code == 404


# =============================================================================
# 4. POST /api/notifications/read-all
# =============================================================================


async def test_read_all_marks_unread_active_returns_count(
    sqlite_engine, notif_client, monkeypatch
):
    """POST /read-all marks every unread-active notification and returns {updated: N}."""
    monkeypatch.setattr("finlytics.notifications.service.REGISTRY", _null_registry())
    factory = _sf(sqlite_engine)

    async with factory() as s:
        u1 = _make_notif(USER_ID)
        u2 = _make_notif(USER_ID)
        u3 = _make_notif(USER_ID)
        already_read = _make_notif(USER_ID, read_at=datetime.now(timezone.utc))
        dismissed = _make_notif(USER_ID, dismissed_at=datetime.now(timezone.utc))
        resolved = _make_notif(USER_ID, resolved_at=datetime.now(timezone.utc))
        s.add_all([u1, u2, u3, already_read, dismissed, resolved])
        await s.commit()
        for n in (u1, u2, u3):
            await s.refresh(n)
        unread_ids = {u1.id, u2.id, u3.id}

    resp = await notif_client.post("/api/notifications/read-all")
    assert resp.status_code == 200
    assert resp.json() == {"updated": 3}

    async with factory() as s:
        rows = (
            await s.execute(
                select(Notification).where(Notification.id.in_(unread_ids))
            )
        ).scalars().all()
        for row in rows:
            assert row.read_at is not None


async def test_read_all_returns_zero_when_nothing_unread(
    sqlite_engine, notif_client, monkeypatch
):
    """POST /read-all returns {updated: 0} when all active notifications are already read."""
    monkeypatch.setattr("finlytics.notifications.service.REGISTRY", _null_registry())
    factory = _sf(sqlite_engine)

    async with factory() as s:
        s.add(_make_notif(USER_ID, read_at=datetime.now(timezone.utc)))
        await s.commit()

    resp = await notif_client.post("/api/notifications/read-all")
    assert resp.status_code == 200
    assert resp.json() == {"updated": 0}


# =============================================================================
# 5. POST /api/notifications/{id}/dismiss
# =============================================================================


async def test_dismiss_removes_from_active_list(sqlite_engine, notif_client, monkeypatch):
    """POST /{id}/dismiss sets dismissed_at; notification disappears from the list."""
    monkeypatch.setattr("finlytics.notifications.service.REGISTRY", _null_registry())
    factory = _sf(sqlite_engine)

    async with factory() as s:
        n = _make_notif(USER_ID)
        s.add(n)
        await s.commit()
        await s.refresh(n)
        notif_id = n.id

    # Pre-dismiss: visible
    assert len((await notif_client.get("/api/notifications")).json()) == 1

    resp = await notif_client.post(f"/api/notifications/{notif_id}/dismiss")
    assert resp.status_code == 204

    # Post-dismiss: hidden
    assert (await notif_client.get("/api/notifications")).json() == []

    async with factory() as s:
        row = (
            await s.execute(select(Notification).where(Notification.id == notif_id))
        ).scalar_one()
        assert row.dismissed_at is not None


async def test_dismiss_404_on_nonexistent(notif_client, monkeypatch):
    """POST /9999/dismiss returns 404 when no such notification exists."""
    monkeypatch.setattr("finlytics.notifications.service.REGISTRY", _null_registry())
    resp = await notif_client.post("/api/notifications/9999/dismiss")
    assert resp.status_code == 404


async def test_dismiss_shields_row_from_auto_resolve(
    sqlite_engine, notif_client, monkeypatch
):
    """A dismissed row is NOT auto-resolved when the condition re-fires.

    Dismiss acts as a permanent shield: the row stays dismissed (resolved_at=None)
    and is excluded from the active list even when the same dedup_key is re-detected.
    """
    dedup_key = "test:condition:shield"
    detected = DetectedNotification(
        source="test",
        type="test_condition",
        severity="warning",
        dedup_key=dedup_key,
        title_key="notif.test",
        title_args={},
    )
    factory = _sf(sqlite_engine)

    # Step 1: condition active → notification created
    monkeypatch.setattr("finlytics.notifications.service.REGISTRY", _registry_with([detected]))
    resp = await notif_client.get("/api/notifications")
    assert len(resp.json()) == 1
    notif_id = resp.json()[0]["id"]

    # Step 2: user dismisses the notification
    assert (await notif_client.post(f"/api/notifications/{notif_id}/dismiss")).status_code == 204

    # Step 3: condition still active — re-evaluate; dismissed row must NOT appear
    monkeypatch.setattr("finlytics.notifications.service.REGISTRY", _registry_with([detected]))
    resp2 = await notif_client.get("/api/notifications")
    assert resp2.json() == []

    # Step 4: DB invariants — dismissed_at set, resolved_at still None
    async with factory() as s:
        row = (
            await s.execute(select(Notification).where(Notification.id == notif_id))
        ).scalar_one()
        assert row.dismissed_at is not None
        assert row.resolved_at is None  # dismiss shield: NOT auto-resolved


# =============================================================================
# 6. Cross-user isolation + ownership 404
# =============================================================================


async def test_list_shows_only_own_notifications(
    sqlite_engine, notif_client, monkeypatch
):
    """GET /notifications for user 1 returns only user 1's active notifications."""
    monkeypatch.setattr("finlytics.notifications.service.REGISTRY", _null_registry())
    factory = _sf(sqlite_engine)

    async with factory() as s:
        u1_notif = _make_notif(USER_ID)
        u2_notif = _make_notif(OTHER_USER_ID)
        s.add_all([u1_notif, u2_notif])
        await s.commit()
        await s.refresh(u1_notif)
        u1_id = u1_notif.id

    resp = await notif_client.get("/api/notifications")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["id"] == u1_id


async def test_unread_count_shows_only_own(sqlite_engine, notif_client, monkeypatch):
    """GET /unread-count for user 1 counts only user 1's unread notifications."""
    monkeypatch.setattr("finlytics.notifications.service.REGISTRY", _null_registry())
    factory = _sf(sqlite_engine)

    async with factory() as s:
        # 1 for user 1, 2 for user 2 — count must return 1
        s.add_all([
            _make_notif(USER_ID),
            _make_notif(OTHER_USER_ID),
            _make_notif(OTHER_USER_ID),
        ])
        await s.commit()

    resp = await notif_client.get("/api/notifications/unread-count")
    assert resp.json() == {"count": 1}


async def test_read_404_on_other_user_notification(sqlite_engine, monkeypatch):
    """POST /{id}/read returns 404 when the notification belongs to a different user."""
    monkeypatch.setattr("finlytics.notifications.service.REGISTRY", _null_registry())
    factory = _sf(sqlite_engine)

    # Insert notification owned by user 1
    async with factory() as s:
        n = _make_notif(USER_ID, dedup_key="test:ownership:read")
        s.add(n)
        await s.commit()
        await s.refresh(n)
        notif_id = n.id

    # Attempt to read it as user 2
    async def _get_db():
        async with factory() as s:
            yield s

    user2 = MagicMock()
    user2.id = OTHER_USER_ID

    async def _get_user():
        return user2

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_current_user] = _get_user
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(f"/api/notifications/{notif_id}/read")
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)

    assert resp.status_code == 404


async def test_dismiss_404_on_other_user_notification(sqlite_engine, monkeypatch):
    """POST /{id}/dismiss returns 404 when the notification belongs to a different user."""
    monkeypatch.setattr("finlytics.notifications.service.REGISTRY", _null_registry())
    factory = _sf(sqlite_engine)

    async with factory() as s:
        n = _make_notif(USER_ID, dedup_key="test:ownership:dismiss")
        s.add(n)
        await s.commit()
        await s.refresh(n)
        notif_id = n.id

    async def _get_db():
        async with factory() as s:
            yield s

    user2 = MagicMock()
    user2.id = OTHER_USER_ID

    async def _get_user():
        return user2

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_current_user] = _get_user
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(f"/api/notifications/{notif_id}/dismiss")
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)

    assert resp.status_code == 404


# =============================================================================
# 7. Unauthenticated — all 5 endpoints return 401
# =============================================================================


async def test_list_401_unauthenticated(unauthenticated_client):
    resp = await unauthenticated_client.get("/api/notifications")
    assert resp.status_code == 401


async def test_unread_count_401_unauthenticated(unauthenticated_client):
    resp = await unauthenticated_client.get("/api/notifications/unread-count")
    assert resp.status_code == 401


async def test_read_all_401_unauthenticated(unauthenticated_client):
    resp = await unauthenticated_client.post("/api/notifications/read-all")
    assert resp.status_code == 401


async def test_mark_read_401_unauthenticated(unauthenticated_client):
    resp = await unauthenticated_client.post("/api/notifications/1/read")
    assert resp.status_code == 401


async def test_dismiss_401_unauthenticated(unauthenticated_client):
    resp = await unauthenticated_client.post("/api/notifications/1/dismiss")
    assert resp.status_code == 401
