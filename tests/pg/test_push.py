"""Push notifications on PostgreSQL: registering a device is an ``INSERT ... ON CONFLICT`` on its
address, and a round claims its deliveries with ``UPDATE ... RETURNING``, so two rounds running
at once never send the same notification twice."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from finlytics.config import settings
from finlytics.db.models import Notification, PushDelivery, PushSubscription, User
from finlytics.notifications import push, webpush
from tests.notifications.push_support import Browser, PushService

SECRET = "a-test-auth-secret-of-enough-length-0123456789"
ORIGIN = "https://finlytics.example.com"


@pytest.fixture
async def owner(sessions: async_sessionmaker[AsyncSession], monkeypatch) -> int:
    monkeypatch.setattr("finlytics.notifications.push.async_session_factory", sessions)
    monkeypatch.setattr(settings, "auth_secret", SECRET)
    monkeypatch.setattr(push, "push_available", lambda: True)
    async with sessions() as s, s.begin():
        user = User(username="owner", password_hash="-")
        s.add(user)
    return user.id


async def register(sessions, owner: int, browser: Browser, *, jti: str, locale: str) -> None:
    keys = browser.subscription()["keys"]
    async with sessions() as db, db.begin():
        await push.register_device(
            db, user_id=owner, token_version=0, session_jti=jti, endpoint=browser.endpoint,
            p256dh=keys["p256dh"], auth=keys["auth"], origin=ORIGIN, locale=locale,
            now=datetime.now(UTC),
        )


async def test_a_device_registers_once_per_address(sessions, owner) -> None:
    browser = Browser()
    await register(sessions, owner, browser, jti="first", locale="es")
    await register(sessions, owner, browser, jti="second", locale="en")

    async with sessions() as db:
        rows = list(await db.scalars(select(PushSubscription)))
    assert [(row.endpoint, row.session_jti, row.locale) for row in rows] == [
        (browser.endpoint, "second", "en")
    ]


async def test_rounds_running_at_once_send_each_notification_once(
    sessions, owner, monkeypatch
) -> None:
    service = PushService()
    monkeypatch.setattr(webpush, "TRANSPORT", httpx.MockTransport(service))
    browser = Browser()
    await register(sessions, owner, browser, jti="session", locale="es")
    now = datetime.now(UTC)
    async with sessions() as db, db.begin():
        alert = Notification(
            user_id=owner, source="statement", type="missing_statement", severity="warning",
            dedup_key="statement:missing:2026-10:acct-1", title_key="notif.statement_missing",
            title_args={"month": "2026-10", "account": "BBVA"}, created_at=now, updated_at=now,
        )
        db.add(alert)
        await db.flush()
        assert await push.enqueue(db, owner, [alert], now) == 1

    claimed = await asyncio.gather(push.push_round(now), push.push_round(now))

    assert sorted(claimed) == [0, 1]
    assert len(service.messages(browser)) == 1
    async with sessions() as db:
        assert list(await db.scalars(select(PushDelivery))) == []
