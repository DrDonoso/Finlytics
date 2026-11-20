"""Push notifications: alerts queued for every active device when they are created, sent at once
(one notification per device and type), retried, dropped and forgotten as the module says."""

from __future__ import annotations

import itertools
from datetime import UTC, date, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from finlytics.config import settings
from finlytics.db.models import (
    Base,
    Notification,
    NotificationPreference,
    PushDelivery,
    PushSubscription,
    User,
)
from finlytics.notifications import push, webpush
from finlytics.notifications.detectors import DetectedNotification
from finlytics.notifications.service import evaluate_notifications
from tests.notifications.push_support import Browser, PushService

SECRET = "a-test-auth-secret-of-enough-length-0123456789"
ORIGIN = "https://finlytics.example.com"
NOW = datetime(2026, 11, 1, 0, 3, tzinfo=UTC)
_keys = itertools.count()


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
    monkeypatch.setattr("finlytics.notifications.push.async_session_factory", session_factory)
    monkeypatch.setattr(settings, "auth_secret", SECRET)
    monkeypatch.setattr(push, "push_available", lambda: True)
    async with session_factory() as db:
        db.add(User(id=1, username="owner", password_hash="-", token_version=0))
        await db.commit()
    yield session_factory
    await engine.dispose()


@pytest.fixture
def service(monkeypatch) -> PushService:
    stand_in = PushService()
    monkeypatch.setattr(webpush, "TRANSPORT", httpx.MockTransport(stand_in))
    return stand_in


async def add_device(
    factory, browser: Browser, *, locale: str = "es", token_version: int = 0
) -> int:
    keys = browser.subscription()["keys"]
    async with factory() as db:
        device = PushSubscription(
            user_id=1, token_version=token_version, session_jti=f"jti-{browser.endpoint[-1]}",
            endpoint=browser.endpoint, p256dh=keys["p256dh"], auth=keys["auth"],
            origin=ORIGIN, locale=locale, failures=0, created_at=NOW, updated_at=NOW,
        )
        db.add(device)
        await db.commit()
        return device.id


def statement(account: str, account_id: int, month: str = "2026-10") -> dict[str, Any]:
    return {
        "source": "statement",
        "args": {"month": month, "account": account},
        "link": f"/finances?account_id={account_id}",
    }


async def add_alerts(factory, *alerts: dict[str, Any], now: datetime = NOW) -> list[int]:
    """Create alerts and queue them, as ``evaluate_notifications`` does."""
    async with factory() as db, db.begin():
        rows = [
            Notification(
                    user_id=1, source=alert["source"], type=alert.get("type", "t"), severity="warning",
                dedup_key=f"{alert['source']}:{next(_keys)}",
                title_key="notif.x", title_args=alert.get("args", {}),
                action_link=alert.get("link"), created_at=now, updated_at=now,
            )
            for alert in alerts
        ]
        db.add_all(rows)
        await db.flush()
        await push.enqueue(db, 1, rows, now)
    return [row.id for row in rows]


async def queued(factory) -> list[PushDelivery]:
    async with factory() as db:
        return list(await db.scalars(select(PushDelivery).order_by(PushDelivery.id)))


async def devices(factory) -> list[PushSubscription]:
    async with factory() as db:
        return list(await db.scalars(select(PushSubscription).order_by(PushSubscription.id)))


async def test_new_alerts_reach_every_active_device_at_once(factory, service) -> None:
    spanish, english = Browser(), Browser(endpoint="https://fcm.googleapis.com/fcm/send/device-2")
    paused = Browser(endpoint="https://web.push.apple.com/device-3")
    await add_device(factory, spanish)
    await add_device(factory, english, locale="en")
    # Its session predates a password change: it waits until the device signs in again.
    await add_device(factory, paused, token_version=-1)
    ids = await add_alerts(factory, statement("BBVA", 3), statement("ING", 4))

    assert await push.push_round(NOW) == 4

    # The statements of one month arrive as one notification per device.
    (message,) = service.messages(spanish)
    assert message == {
        "web_push": 8030,
        "notification": {
            "title": "2 extractos pendientes",
            "body": "Falta subir el extracto de octubre de 2026 de BBVA e ING.",
            "lang": "es-ES",
            "dir": "ltr",
            "navigate": f"{ORIGIN}/?notif={ids[0]},{ids[1]}",
            "tag": f"alert-{ids[0]}",
            "silent": False,
            "icon": f"{ORIGIN}/icon-192.png",
            "badge": f"{ORIGIN}/badge-96.png",
        },
        "app_badge": 2,
    }
    (message,) = service.messages(english)
    assert message["notification"]["title"] == "2 missing statements"
    assert message["notification"]["body"] == (
        "The October 2026 statements of BBVA and ING haven't been imported yet."
    )
    assert service.messages(paused) == []
    assert await queued(factory) == []


async def test_each_alert_type_tells_what_it_is_and_opens_its_page(factory, service) -> None:
    browser = Browser()
    await add_device(factory, browser)
    first = await add_alerts(factory, statement("Revolut", 7))
    second = await add_alerts(
        factory,
        {"source": "espp", "args": {"period": "Q3 2026"}, "link": "/investments/fidelity-espp"},
        {"source": "future", "args": {}, "link": "https://elsewhere.example.com"},
    )
    shares = "/investments/fidelity-espp"
    third = await add_alerts(
        factory,
        *(
            {"source": "modelo720", "type": f"modelo720_{verdict}", "args": {"year": "2026"},
             "link": shares}
            for verdict in ("exceeds", "below")
        ),
    )

    await push.push_round(NOW)

    told = [message["notification"] for message in service.messages(browser)]
    assert [(item["title"], item["body"], item["navigate"]) for item in told] == [
        (
            "Extracto pendiente: Revolut",
            "Falta subir el extracto de octubre de 2026.",
            f"{ORIGIN}/finances?account_id=7&notif={first[0]}",
        ),
        (
            "Subida ESPP pendiente",
            "Falta importar el CSV del ESPP de Q3 2026.",
            f"{ORIGIN}/investments/fidelity-espp?notif={second[0]}",
        ),
        # A type without texts of its own still says something, and only opens Finlytics.
        (
            "Nueva alerta",
            "Ábrela en Finlytics para ver los detalles.",
            f"{ORIGIN}/?notif={second[1]}",
        ),
        # The verdict, never the figures.
        (
            "Modelo 720 (ejercicio 2026): superas el umbral",
            (
                "Tus acciones de Fidelity lo superaban a 31 de diciembre. "
                "El plazo acaba el 31 de marzo."
            ),
            f"{ORIGIN}{shares}?notif={third[0]}",
        ),
        (
            "Modelo 720 (ejercicio 2026): no superas el umbral",
            (
                "Tus acciones de Fidelity no lo superaban a 31 de diciembre: "
                "por ellas no tienes que presentarlo."
            ),
            f"{ORIGIN}{shares}?notif={third[1]}",
        ),
    ]


async def test_alerts_created_by_the_detectors_are_queued_in_the_same_transaction(
    factory, service, monkeypatch
) -> None:
    browser = Browser()
    await add_device(factory, browser)
    detector = AsyncMock()
    detector.id = "statement"
    detector.is_condition = True
    detector.evaluate = AsyncMock(return_value=[
        DetectedNotification(
            source="statement", type="missing_statement", severity="warning",
            dedup_key="statement:missing:2026-10:acct-3", title_key="notif.statement_missing",
            title_args={"month": "2026-10", "account": "BBVA"},
            action_link="/finances?account_id=3",
        )
    ])
    monkeypatch.setattr("finlytics.notifications.service.REGISTRY", [detector])

    async with factory() as db:
        assert len(await evaluate_notifications(db, 1, today=date(2026, 11, 1))) == 1
        # Evaluating again creates nothing, so nothing is told twice.
        assert await evaluate_notifications(db, 1, today=date(2026, 11, 1)) == []
    assert len(await queued(factory)) == 1

    await push.push_round()
    (message,) = service.messages(browser)
    assert message["notification"]["title"] == "Extracto pendiente: BBVA"


async def test_alerts_read_dismissed_resolved_or_muted_meanwhile_are_not_sent(
    factory, service
) -> None:
    browser = Browser()
    await add_device(factory, browser)
    read, dismissed, resolved, _, kept = await add_alerts(
        factory,
        statement("A", 1, "2026-06"),
        statement("B", 2, "2026-07"),
        statement("C", 3, "2026-08"),
        {"source": "espp", "args": {"period": "Q3 2026"}},
        statement("D", 4, "2026-09"),
    )
    async with factory() as db, db.begin():
        for column, alert_id in (("read_at", read), ("dismissed_at", dismissed),
                                 ("resolved_at", resolved)):
            await db.execute(
                update(Notification).where(Notification.id == alert_id).values({column: NOW})
            )
        db.add(NotificationPreference(user_id=1, source="espp", enabled=False))

    await push.push_round(NOW)

    told = service.messages(browser)
    assert [message["notification"]["navigate"] for message in told] == [
        f"{ORIGIN}/finances?account_id=4&notif={kept}"
    ]
    # The badge counts what is still unread: D and the muted ESPP upload.
    assert told[0]["app_badge"] == 2
    assert await queued(factory) == []


async def test_muted_types_are_not_queued(factory, service) -> None:
    await add_device(factory, Browser())
    async with factory() as db, db.begin():
        db.add(NotificationPreference(user_id=1, source="statement", enabled=False))
    await add_alerts(factory, statement("BBVA", 3))
    assert await queued(factory) == []


async def test_a_failed_send_is_retried_until_the_window_closes(factory, service) -> None:
    browser = Browser()
    await add_device(factory, browser)
    await add_alerts(factory, statement("BBVA", 3))
    service.status = None

    await push.push_round(NOW)
    (delivery,) = await queued(factory)
    assert delivery.attempts == 1
    assert push.aware(delivery.next_attempt_at) == NOW + timedelta(minutes=2)
    # Not due yet: nothing is tried.
    assert await push.push_round(NOW + timedelta(minutes=1)) == 0

    service.status = 201
    service.requests.clear()
    await push.push_round(NOW + timedelta(minutes=2))
    assert len(service.messages(browser)) == 1
    assert await queued(factory) == []

    # One that keeps failing is given up once a day has gone by.
    await add_alerts(factory, statement("ING", 4))
    service.status = 503
    moment = NOW
    while await queued(factory):
        await push.push_round(moment)
        moment += timedelta(minutes=61)
    assert moment - NOW > push.DELIVERY_WINDOW - timedelta(hours=2)
    assert len(await devices(factory)) == 1


async def test_a_claimed_delivery_waits_for_its_lease(factory, service) -> None:
    browser = Browser()
    await add_device(factory, browser)
    await add_alerts(factory, statement("BBVA", 3))

    # A round that claimed it and never recorded the outcome (another worker, a crash).
    groups, _, claimed = await push._claim(NOW)
    assert (len(groups), claimed) == (1, 1)
    assert await push.push_round(NOW) == 0
    assert service.messages(browser) == []

    await push.push_round(NOW + push.CLAIM_LEASE)
    assert len(service.messages(browser)) == 1


async def test_a_device_its_push_service_forgot_is_forgotten(factory, service) -> None:
    await add_device(factory, Browser())
    await add_alerts(factory, statement("BBVA", 3), {"source": "espp", "args": {}})
    service.status = 410

    await push.push_round(NOW)

    # One request: what else was queued for it goes with the device.
    assert len(service.requests) == 1
    assert await devices(factory) == []
    assert await queued(factory) == []


async def test_a_device_refused_three_times_in_a_row_is_forgotten(factory, service) -> None:
    await add_device(factory, Browser())
    service.status = 403
    for month in ("2026-08", "2026-09"):
        await add_alerts(factory, statement("BBVA", 3, month))
        await push.push_round(NOW)
    assert [device.failures for device in await devices(factory)] == [2]

    # A delivery in between starts the count again.
    service.status = 201
    await add_alerts(factory, statement("BBVA", 3, "2026-10"))
    await push.push_round(NOW)
    assert [device.failures for device in await devices(factory)] == [0]

    service.status = 403
    for month in ("2026-11", "2026-12", "2027-01"):
        await add_alerts(factory, statement("BBVA", 3, month))
        await push.push_round(NOW)
    assert await devices(factory) == []


async def test_nothing_is_queued_or_sent_without_a_configured_auth_secret(
    factory, service, monkeypatch
) -> None:
    await add_device(factory, Browser())
    monkeypatch.setattr(push, "push_available", lambda: False)

    await add_alerts(factory, statement("BBVA", 3))

    assert push.public_key() is None
    assert await queued(factory) == []
    assert await push.push_round(NOW) == 0
    assert service.requests == []


@pytest.mark.parametrize(
    ("origin", "expected"),
    [
        ("https://finlytics.example.com", "https://finlytics.example.com"),
        ("https://Finlytics.Example.com:8443", "https://finlytics.example.com:8443"),
        ("http://localhost:5173", "http://localhost:5173"),
        ("http://127.0.0.1:7777", "http://127.0.0.1:7777"),
        ("http://192.168.1.20:7777", None),
        ("https://finlytics.example.com/settings", None),
        ("https://user@finlytics.example.com", None),
        ("null", None),
        ("", None),
        (None, None),
    ],
)
def test_devices_register_from_secure_origins_only(origin: str | None, expected: str | None):
    assert push.device_origin(origin) == expected


@pytest.mark.parametrize(
    ("path", "ids", "expected"),
    [
        ("/finances?account_id=3", [5], "/finances?account_id=3&notif=5"),
        ("/investments/fidelity-espp", [1, 2], "/investments/fidelity-espp?notif=1,2"),
        ("/statements#2026-10", [9], "/statements?notif=9#2026-10"),
        (None, [4], "/?notif=4"),
        ("//evil.example.com", [4], "/?notif=4"),
    ],
)
def test_a_notification_opens_an_in_app_page(path: str | None, ids: list[int], expected: str):
    assert push.with_intent(path, ids) == expected


def test_month_names_and_lists_follow_each_language() -> None:
    assert push.month_label("2026-01", "es") == "enero de 2026"
    assert push.month_label("2026-12", "en") == "December 2026"
    assert push.month_label("garbage", "es") == "garbage"
    assert push.listed(["BBVA", "Revolut", "Santander"], "es") == "BBVA, Revolut y Santander"
    assert push.listed(["BBVA", "Hipotecas"], "es") == "BBVA e Hipotecas"
    assert push.listed(["BBVA", "Hielo"], "es") == "BBVA y Hielo"
    assert push.listed(["BBVA", "ING"], "en") == "BBVA and ING"
