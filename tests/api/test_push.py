"""/api/push and /api/notifications/preferences against a real in-memory database and real
sessions: a device registers for its session, is refused where push cannot work, follows a
re-issued session and stops when it signs out.

Each ``AsyncClient`` plays one device: its cookie jar holds that device's session.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from finlytics.api.deps import get_db
from finlytics.app import app
from finlytics.auth.security import decode_token, hash_password
from finlytics.config import settings
from finlytics.db.models import Base, Notification, PushDelivery, PushSubscription, User
from finlytics.notifications import push, webpush
from tests.notifications.push_support import Browser, PushService

USERNAME = "drdonoso"
PASSWORD = "MyStr0ngP@ss!"
NEW_PASSWORD = "An0ther-Str0ng-One"
COOKIE = "finlytics_session"
SECRET = "a-test-auth-secret-of-enough-length-0123456789"
ORIGIN = "https://finlytics.example.com"


@pytest.fixture
async def factory(monkeypatch):
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _get_db():
        async with session_factory() as s:
            yield s

    monkeypatch.setattr("finlytics.api.deps.async_session_factory", session_factory)
    monkeypatch.setattr("finlytics.notifications.push.async_session_factory", session_factory)
    monkeypatch.setattr("finlytics.auth.security._BCRYPT_ROUNDS", 4)
    monkeypatch.setattr(settings, "auth_cookie_secure", False)
    monkeypatch.setattr(settings, "auth_secret", SECRET)
    monkeypatch.setattr(push, "push_available", lambda: True)
    app.dependency_overrides[get_db] = _get_db

    async with session_factory() as s:
        s.add(User(username=USERNAME, password_hash=hash_password(PASSWORD)))
        await s.commit()

    yield session_factory

    app.dependency_overrides.pop(get_db, None)
    await engine.dispose()


@pytest.fixture
def service(monkeypatch) -> PushService:
    stand_in = PushService()
    monkeypatch.setattr(webpush, "TRANSPORT", httpx.MockTransport(stand_in))
    return stand_in


@asynccontextmanager
async def _device(origin: str | None = ORIGIN) -> AsyncIterator[AsyncClient]:
    headers = {"Origin": origin} if origin else {}
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url=ORIGIN, headers=headers
    ) as client:
        yield client


async def _login(device: AsyncClient) -> str:
    """Sign the device in; the id of its session."""
    resp = await device.post("/api/auth/login", json={"username": USERNAME, "password": PASSWORD})
    assert resp.status_code == 200, resp.text
    return decode_token(resp.cookies[COOKIE])["jti"]


def _jti(device: AsyncClient) -> str:
    return decode_token(device.cookies[COOKIE])["jti"]


async def _devices(factory) -> list[PushSubscription]:
    async with factory() as db:
        return list(await db.scalars(select(PushSubscription).order_by(PushSubscription.id)))


async def test_the_key_browsers_subscribe_with(factory, monkeypatch) -> None:
    async with _device() as device:
        assert (await device.get("/api/push")).status_code == 401
        await _login(device)
        key = webpush.b64encode(webpush.public_bytes(webpush.vapid_key(SECRET)))
        assert (await device.get("/api/push")).json() == {"public_key": key}
        monkeypatch.setattr(push, "push_available", lambda: False)
        assert (await device.get("/api/push")).json() == {"public_key": None}


async def test_a_device_registers_for_its_session_and_refreshes_it(factory) -> None:
    browser = Browser()
    async with _device() as device:
        jti = await _login(device)
        resp = await device.put("/api/push/subscription", json=browser.subscription())
        assert resp.status_code == 204, resp.text
        resp = await device.put("/api/push/subscription", json=browser.subscription(locale="en"))
        assert resp.status_code == 204, resp.text

    (row,) = await _devices(factory)
    assert (row.endpoint, row.session_jti, row.token_version, row.origin, row.locale) == (
        browser.endpoint, jti, 0, ORIGIN, "en",
    )


@pytest.mark.parametrize(
    ("change", "origin", "status"),
    [
        ({"endpoint": "https://push.example.net/device"}, ORIGIN, 422),
        ({"keys": {"p256dh": "not-a-key", "auth": "AAAAAAAAAAAAAAAAAAAAAA"}}, ORIGIN, 422),
        ({}, "http://192.168.1.20:7777", 422),
        ({}, None, 422),
        ({"locale": "pt"}, ORIGIN, 422),
    ],
)
async def test_registrations_that_cannot_work_are_refused(
    factory, change: dict, origin: str | None, status: int
) -> None:
    async with _device(origin) as device:
        await _login(device)
        resp = await device.put("/api/push/subscription", json=Browser().subscription(**change))
    assert resp.status_code == status
    assert await _devices(factory) == []


async def test_nothing_registers_while_push_is_unavailable(factory, monkeypatch) -> None:
    monkeypatch.setattr(push, "push_available", lambda: False)
    async with _device() as device:
        await _login(device)
        resp = await device.put("/api/push/subscription", json=Browser().subscription())
    assert resp.status_code == 503
    assert "AUTH_SECRET" in resp.json()["detail"]


async def test_a_user_keeps_the_ten_most_recent_devices(factory) -> None:
    browsers = [Browser(endpoint=f"https://web.push.apple.com/device-{n}") for n in range(11)]
    async with _device() as device:
        await _login(device)
        for browser in browsers:
            resp = await device.put("/api/push/subscription", json=browser.subscription())
            assert resp.status_code == 204
    kept = [row.endpoint for row in await _devices(factory)]
    assert len(kept) == push.MAX_DEVICES
    assert browsers[0].endpoint not in kept


async def test_unsubscribing_forgets_the_device(factory) -> None:
    browser = Browser()
    async with _device() as device:
        await _login(device)
        await device.put("/api/push/subscription", json=browser.subscription())
        resp = await device.post("/api/push/unsubscribe", json={"endpoint": browser.endpoint})
    assert resp.status_code == 204
    assert await _devices(factory) == []


async def test_a_test_notification_reaches_the_device(factory, service) -> None:
    browser = Browser()
    async with _device() as device:
        await _login(device)
        await device.put("/api/push/subscription", json=browser.subscription())
        resp = await device.post("/api/push/test", json={"endpoint": browser.endpoint})
        assert resp.json() == {"ok": True, "error": None}
        (message,) = service.messages(browser)
        assert message["notification"]["title"] == "Notificación de prueba"
        assert message["notification"]["navigate"] == f"{ORIGIN}/settings/notifications"

        service.status = 503
        resp = await device.post("/api/push/test", json={"endpoint": browser.endpoint})
        assert resp.json() == {"ok": False, "error": "unreachable"}

        missing = await device.post("/api/push/test", json={"endpoint": "https://fcm.googleapis.com/x"})
        assert missing.status_code == 404

        # Its push service no longer knows it: the device is forgotten.
        service.status = 410
        resp = await device.post("/api/push/test", json={"endpoint": browser.endpoint})
        assert resp.json() == {"ok": False, "error": "gone"}
    assert await _devices(factory) == []


async def test_signing_out_stops_the_device(factory) -> None:
    kept, signed_out = Browser(endpoint="https://web.push.apple.com/kept"), Browser()
    async with _device() as phone, _device() as laptop:
        await _login(phone)
        await _login(laptop)
        await phone.put("/api/push/subscription", json=kept.subscription())
        await laptop.put("/api/push/subscription", json=signed_out.subscription())
        assert (await laptop.post("/api/auth/logout")).status_code == 200
    assert [row.endpoint for row in await _devices(factory)] == [kept.endpoint]


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/api/auth/password", {"current_password": PASSWORD, "new_password": NEW_PASSWORD}),
        ("/api/auth/logout-others", None),
    ],
)
async def test_a_reissued_session_keeps_this_device_and_pauses_the_others(
    factory, path: str, body: dict | None
) -> None:
    here, elsewhere = Browser(endpoint="https://web.push.apple.com/here"), Browser()
    async with _device() as phone, _device() as laptop:
        await _login(phone)
        old_laptop_jti = await _login(laptop)
        await phone.put("/api/push/subscription", json=here.subscription())
        await laptop.put("/api/push/subscription", json=elsewhere.subscription())

        assert (await phone.post(path, json=body)).status_code == 200
        new_phone_jti = _jti(phone)

    rows = {row.endpoint: row for row in await _devices(factory)}
    assert (rows[here.endpoint].session_jti, rows[here.endpoint].token_version) == (
        new_phone_jti, 1,
    )
    assert (rows[elsewhere.endpoint].session_jti, rows[elsewhere.endpoint].token_version) == (
        old_laptop_jti, 0,
    )

    # Only the device that is still signed in is told about a new alert.
    now = datetime.now(UTC)
    async with factory() as db, db.begin():
        alert = Notification(
            user_id=1, source="statement", type="missing_statement", severity="warning",
            dedup_key="statement:missing:2026-10:acct-1", title_key="notif.statement_missing",
            title_args={"month": "2026-10", "account": "BBVA"}, created_at=now, updated_at=now,
        )
        db.add(alert)
        await db.flush()
        await push.enqueue(db, 1, [alert], now)
    async with factory() as db:
        queued = list(await db.scalars(select(PushDelivery.subscription_id)))
    assert queued == [rows[here.endpoint].id]


async def test_each_alert_type_can_be_muted(factory) -> None:
    async with _device() as device:
        await _login(device)
        assert (await device.get("/api/notifications/preferences")).json() == [
            {"source": "statement", "enabled": True},
            {"source": "espp", "enabled": True},
        ]
        resp = await device.patch(
            "/api/notifications/preferences", json={"source": "espp", "enabled": False}
        )
        assert resp.json() == [
            {"source": "statement", "enabled": True},
            {"source": "espp", "enabled": False},
        ]
        await device.patch(
            "/api/notifications/preferences", json={"source": "espp", "enabled": True}
        )
        assert (await device.get("/api/notifications/preferences")).json()[1]["enabled"] is True

        unknown = await device.patch(
            "/api/notifications/preferences", json={"source": "nope", "enabled": False}
        )
        assert unknown.status_code == 422
