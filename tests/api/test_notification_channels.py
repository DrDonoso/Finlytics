"""API-level tests for /api/notifications channel endpoints (Slice 2 — Telegram).

Test areas:
1. GET  /notifications/channels  — list, field shape, no-secrets invariant, cross-user isolation
2. POST /notifications/channels  — upsert, masked label, TelegramError→400, no-token-leak,
                                   EncryptionNotConfiguredError→503
3. DELETE /notifications/channels/{id} — 204/404 ownership
4. POST /notifications/channels/telegram/test — both-creds success/fail, partial creds, stored channel
5. deliver_new integration via evaluate — first evaluate sends once; second evaluate no re-send
6. Unauthenticated → 401 on all four channel endpoints

Patch sites (names as imported/used in production modules):
  finlytics.api.notifications.telegram_get_me          — POST /channels validation
  finlytics.api.notifications.telegram_send_message    — POST /channels/telegram/test
  finlytics.api.notifications.encrypt_token            — POST /channels config encryption
  finlytics.api.notifications.decrypt_token            — POST /channels/telegram/test stored-channel
  finlytics.notifications.service.telegram_send_message — deliver_new Telegram send
  finlytics.notifications.service.decrypt_token         — deliver_new config decrypt

StaticPool note: all sessions share ONE underlying connection; setup/assertion blocks
use short-lived ``async with factory() as s:`` sessions so the connection is idle
when the HTTP client acquires it.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from finlytics.api.deps import get_current_user, get_db
from finlytics.app import app
from finlytics.db.models import Base, NotificationChannel, NotificationDelivery
from finlytics.investments.crypto import EncryptionNotConfiguredError
from finlytics.notifications.detectors import DetectedNotification
from finlytics.notifications.telegram import TelegramError

USER_ID = 1
OTHER_USER_ID = 2

# Safe test placeholders — NOT real-looking tokens
_BOT_TOKEN = "test:placeholder_bot_token"
_CHAT_ID = "987654321"
_DECRYPTED_CONFIG = json.dumps({"bot_token": _BOT_TOKEN, "chat_id": _CHAT_ID})


# ── Registry helpers ──────────────────────────────────────────────────────────


def _null_registry():
    """No detectors — pre-inserted rows are untouched by evaluate."""
    return []


def _registry_with(detected: list[DetectedNotification]):
    """One detector with id='test' returning the given notifications every call."""
    d = AsyncMock()
    d.id = "test"
    d.is_condition = True
    d.evaluate = AsyncMock(return_value=detected)
    return [d]


# ── ORM helpers ───────────────────────────────────────────────────────────────


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make_channel(
    user_id: int = USER_ID,
    chat_id_suffix: str = "4321",
) -> NotificationChannel:
    return NotificationChannel(
        user_id=user_id,
        channel="telegram",
        config_enc="dummy_ciphertext",
        label=f"Telegram · ••••{chat_id_suffix}",
        enabled=True,
        created_at=_now(),
        updated_at=_now(),
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
    """ASGI client wired to the in-memory SQLite DB; auth = user_id=USER_ID."""
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
    """Only get_db overridden; real get_current_user raises 401 (no session cookie)."""
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
    """Return a session factory for *engine*."""
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# =============================================================================
# 1. GET /api/notifications/channels
# =============================================================================


async def test_list_channels_empty(notif_client):
    """No configured channels → 200, empty list."""
    resp = await notif_client.get("/api/notifications/channels")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_channels_field_shape(sqlite_engine, notif_client):
    """Channel exists → response contains exactly {id, channel, label, enabled, created_at}."""
    factory = _sf(sqlite_engine)
    async with factory() as s:
        s.add(_make_channel())
        await s.commit()

    resp = await notif_client.get("/api/notifications/channels")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert set(data[0].keys()) == {"id", "channel", "label", "enabled", "created_at"}


async def test_list_channels_no_secret_fields(sqlite_engine, notif_client):
    """Response body must NEVER contain config_enc, bot_token, or chat_id."""
    factory = _sf(sqlite_engine)
    async with factory() as s:
        s.add(_make_channel())
        await s.commit()

    resp = await notif_client.get("/api/notifications/channels")
    assert resp.status_code == 200
    body = resp.text
    assert "config_enc" not in body
    assert "bot_token" not in body
    assert "chat_id" not in body


async def test_list_channels_label_is_masked(sqlite_engine, notif_client):
    """Label shows ••••{last4} of the chat_id — never the full identifier."""
    factory = _sf(sqlite_engine)
    async with factory() as s:
        s.add(_make_channel(chat_id_suffix="1234"))
        await s.commit()

    resp = await notif_client.get("/api/notifications/channels")
    assert resp.status_code == 200
    label = resp.json()[0]["label"]
    assert "••••" in label
    assert "1234" in label


async def test_list_channels_hides_other_user_channel(sqlite_engine, notif_client):
    """A channel belonging to another user is NOT returned."""
    factory = _sf(sqlite_engine)
    async with factory() as s:
        s.add(_make_channel(user_id=OTHER_USER_ID))
        await s.commit()

    resp = await notif_client.get("/api/notifications/channels")
    assert resp.status_code == 200
    assert resp.json() == []


# =============================================================================
# 2. POST /api/notifications/channels
# =============================================================================


async def test_post_channel_success_201(notif_client):
    """Valid token (getMe patched) → 201, correct NotificationChannelOut shape."""
    with (
        patch(
            "finlytics.api.notifications.telegram_get_me",
            new_callable=AsyncMock,
            return_value={"id": 42, "username": "testbot"},
        ),
        patch("finlytics.api.notifications.encrypt_token", return_value="encrypted_blob"),
    ):
        resp = await notif_client.post(
            "/api/notifications/channels",
            json={"bot_token": _BOT_TOKEN, "chat_id": _CHAT_ID},
        )
    assert resp.status_code == 201
    data = resp.json()
    assert data["channel"] == "telegram"
    assert data["enabled"] is True
    assert "id" in data
    assert "created_at" in data


async def test_post_channel_label_masked(notif_client):
    """Returned label shows last 4 chars of chat_id prefixed with ••••."""
    with (
        patch(
            "finlytics.api.notifications.telegram_get_me",
            new_callable=AsyncMock,
            return_value={"id": 42, "username": "testbot"},
        ),
        patch("finlytics.api.notifications.encrypt_token", return_value="encrypted_blob"),
    ):
        resp = await notif_client.post(
            "/api/notifications/channels",
            json={"bot_token": _BOT_TOKEN, "chat_id": "123456789"},
        )
    assert resp.status_code == 201
    # Last 4 of "123456789" → "6789"
    assert resp.json()["label"] == "Telegram · ••••6789"


async def test_post_channel_response_no_secrets(notif_client):
    """201 response body must not expose config_enc, bot_token, or the raw chat_id key."""
    with (
        patch(
            "finlytics.api.notifications.telegram_get_me",
            new_callable=AsyncMock,
            return_value={"id": 42, "username": "testbot"},
        ),
        patch("finlytics.api.notifications.encrypt_token", return_value="encrypted_blob"),
    ):
        resp = await notif_client.post(
            "/api/notifications/channels",
            json={"bot_token": _BOT_TOKEN, "chat_id": _CHAT_ID},
        )
    assert resp.status_code == 201
    body = resp.text
    assert "config_enc" not in body
    assert _BOT_TOKEN not in body
    assert "bot_token" not in body
    # "chat_id" key must not appear (label only contains the last-4 suffix)
    assert "chat_id" not in body


async def test_post_channel_upsert_one_row(sqlite_engine, notif_client):
    """POSTing twice replaces the existing channel — only one row exists in the DB."""
    factory = _sf(sqlite_engine)

    with (
        patch(
            "finlytics.api.notifications.telegram_get_me",
            new_callable=AsyncMock,
            return_value={"id": 42, "username": "testbot"},
        ),
        patch(
            "finlytics.api.notifications.encrypt_token",
            side_effect=["enc_v1", "enc_v2"],
        ),
    ):
        r1 = await notif_client.post(
            "/api/notifications/channels",
            json={"bot_token": _BOT_TOKEN, "chat_id": "111111"},
        )
        r2 = await notif_client.post(
            "/api/notifications/channels",
            json={"bot_token": _BOT_TOKEN, "chat_id": "222222"},
        )

    assert r1.status_code == 201
    assert r2.status_code == 201

    async with factory() as s:
        rows = (await s.execute(select(NotificationChannel))).scalars().all()
    assert len(rows) == 1
    # Second POST updated the label to reflect the new chat_id
    assert rows[0].label == "Telegram · ••••2222"


async def test_post_channel_telegram_error_400(notif_client):
    """Invalid token (getMe raises TelegramError) → 400."""
    with patch(
        "finlytics.api.notifications.telegram_get_me",
        new_callable=AsyncMock,
        side_effect=TelegramError("Telegram token rejected: Bad Request"),
    ):
        resp = await notif_client.post(
            "/api/notifications/channels",
            json={"bot_token": _BOT_TOKEN, "chat_id": _CHAT_ID},
        )
    assert resp.status_code == 400


async def test_post_channel_error_body_no_token_leak(notif_client):
    """The 400 response body must NOT contain the submitted bot_token."""
    token_sentinel = "sentinel_secret_token_leak_check"
    with patch(
        "finlytics.api.notifications.telegram_get_me",
        new_callable=AsyncMock,
        side_effect=TelegramError("Telegram token rejected: Bad Request"),
    ):
        resp = await notif_client.post(
            "/api/notifications/channels",
            json={"bot_token": token_sentinel, "chat_id": _CHAT_ID},
        )
    assert resp.status_code == 400
    assert token_sentinel not in resp.text


async def test_post_channel_encrypt_fail_503(notif_client):
    """Missing encryption key (EncryptionNotConfiguredError) → 503."""
    with (
        patch(
            "finlytics.api.notifications.telegram_get_me",
            new_callable=AsyncMock,
            return_value={"id": 42, "username": "testbot"},
        ),
        patch(
            "finlytics.api.notifications.encrypt_token",
            side_effect=EncryptionNotConfiguredError("no key"),
        ),
    ):
        resp = await notif_client.post(
            "/api/notifications/channels",
            json={"bot_token": _BOT_TOKEN, "chat_id": _CHAT_ID},
        )
    assert resp.status_code == 503


# =============================================================================
# 3. DELETE /api/notifications/channels/{id}
# =============================================================================


async def test_delete_channel_204(sqlite_engine, notif_client):
    """Deleting own channel returns 204 and removes the row from the DB."""
    factory = _sf(sqlite_engine)
    async with factory() as s:
        ch = _make_channel()
        s.add(ch)
        await s.commit()
        await s.refresh(ch)
        ch_id = ch.id

    resp = await notif_client.delete(f"/api/notifications/channels/{ch_id}")
    assert resp.status_code == 204

    async with factory() as s:
        row = (await s.execute(select(NotificationChannel))).scalar_one_or_none()
    assert row is None


async def test_delete_channel_other_user_404(sqlite_engine, notif_client):
    """A channel owned by another user returns 404 (ownership enforced)."""
    factory = _sf(sqlite_engine)
    async with factory() as s:
        ch = _make_channel(user_id=OTHER_USER_ID)
        s.add(ch)
        await s.commit()
        await s.refresh(ch)
        ch_id = ch.id

    resp = await notif_client.delete(f"/api/notifications/channels/{ch_id}")
    assert resp.status_code == 404


async def test_delete_channel_nonexistent_404(notif_client):
    """Deleting a non-existent channel id returns 404."""
    resp = await notif_client.delete("/api/notifications/channels/99999")
    assert resp.status_code == 404


# =============================================================================
# 4. POST /api/notifications/channels/telegram/test
# =============================================================================


async def test_test_channel_both_creds_ok(notif_client):
    """Providing both bot_token + chat_id and a successful send → {ok: true}."""
    with patch(
        "finlytics.api.notifications.telegram_send_message",
        new_callable=AsyncMock,
    ):
        resp = await notif_client.post(
            "/api/notifications/channels/telegram/test",
            json={"bot_token": _BOT_TOKEN, "chat_id": _CHAT_ID},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data.get("error") is None


async def test_test_channel_send_fail_ok_false_no_token_leak(notif_client):
    """TelegramError during send → HTTP 200 {ok: false, error:...}; token absent from body."""
    token_sentinel = "sentinel_telegram_test_token"
    with patch(
        "finlytics.api.notifications.telegram_send_message",
        new_callable=AsyncMock,
        side_effect=TelegramError("sendMessage failed (HTTP 403)."),
    ):
        resp = await notif_client.post(
            "/api/notifications/channels/telegram/test",
            json={"bot_token": token_sentinel, "chat_id": _CHAT_ID},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is False
    assert data.get("error") is not None
    # Token must NOT appear anywhere in the response body
    assert token_sentinel not in resp.text


async def test_test_channel_only_bot_token_400(notif_client):
    """Supplying only bot_token (without chat_id) is rejected as incomplete config."""
    resp = await notif_client.post(
        "/api/notifications/channels/telegram/test",
        json={"bot_token": _BOT_TOKEN},
    )
    assert resp.status_code == 400


async def test_test_channel_only_chat_id_400(notif_client):
    """Supplying only chat_id (without bot_token) is rejected as incomplete config."""
    resp = await notif_client.post(
        "/api/notifications/channels/telegram/test",
        json={"chat_id": _CHAT_ID},
    )
    assert resp.status_code == 400


async def test_test_channel_no_creds_no_channel_400(notif_client):
    """Empty body with no stored channel → 400 (nothing to test against)."""
    resp = await notif_client.post(
        "/api/notifications/channels/telegram/test",
        json={},
    )
    assert resp.status_code == 400


async def test_test_channel_stored_channel_ok(sqlite_engine, notif_client):
    """Empty body with a stored channel → uses stored creds (patched decrypt/send) → {ok: true}."""
    factory = _sf(sqlite_engine)
    async with factory() as s:
        s.add(_make_channel())
        await s.commit()

    with (
        patch("finlytics.api.notifications.decrypt_token", return_value=_DECRYPTED_CONFIG),
        patch("finlytics.api.notifications.telegram_send_message", new_callable=AsyncMock),
    ):
        resp = await notif_client.post(
            "/api/notifications/channels/telegram/test",
            json={},
        )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


# =============================================================================
# 5. deliver_new integration via evaluate_notifications
#
# These test the FULL path: GET /notifications → evaluate_notifications →
# deliver_new → telegram_send_message.  They complement Shuri's direct
# deliver_new unit tests by exercising the evaluate → deliver seam.
# =============================================================================


async def test_evaluate_delivers_via_channel_once(sqlite_engine, notif_client, monkeypatch):
    """A newly detected notification is delivered exactly once through the channel."""
    factory = _sf(sqlite_engine)
    async with factory() as s:
        s.add(_make_channel())
        await s.commit()

    detected = DetectedNotification(
        source="test",
        type="test_type",
        severity="info",
        dedup_key="test:integration:chan:001",
        title_key="notif.statement_missing",
        title_args={"account": "BBVA", "month": "2026-06"},
    )
    monkeypatch.setattr("finlytics.notifications.service.REGISTRY", _registry_with([detected]))

    with (
        patch("finlytics.notifications.service.decrypt_token", return_value=_DECRYPTED_CONFIG),
        patch(
            "finlytics.notifications.service.telegram_send_message",
            new_callable=AsyncMock,
        ) as mock_send,
    ):
        resp = await notif_client.get("/api/notifications")

    assert resp.status_code == 200
    mock_send.assert_called_once()

    async with factory() as s:
        deliveries = (await s.execute(select(NotificationDelivery))).scalars().all()
    assert len(deliveries) == 1
    assert deliveries[0].status == "sent"
    assert deliveries[0].channel == "telegram"


async def test_evaluate_second_call_no_resend(sqlite_engine, notif_client, monkeypatch):
    """Second evaluate of the same condition does NOT re-deliver (notif already exists)."""
    factory = _sf(sqlite_engine)
    async with factory() as s:
        s.add(_make_channel())
        await s.commit()

    detected = DetectedNotification(
        source="test",
        type="test_type",
        severity="info",
        dedup_key="test:integration:chan:002",
        title_key="notif.statement_missing",
        title_args={"account": "BBVA", "month": "2026-07"},
    )
    monkeypatch.setattr("finlytics.notifications.service.REGISTRY", _registry_with([detected]))

    with (
        patch("finlytics.notifications.service.decrypt_token", return_value=_DECRYPTED_CONFIG),
        patch(
            "finlytics.notifications.service.telegram_send_message",
            new_callable=AsyncMock,
        ) as mock_send,
    ):
        # First call: notification created → delivered
        resp1 = await notif_client.get("/api/notifications")
        # Second call: notification already exists → new_notifs=[] → no delivery
        resp2 = await notif_client.get("/api/notifications")

    assert resp1.status_code == 200
    assert resp2.status_code == 200
    # Telegram send called exactly once across both evaluates
    mock_send.assert_called_once()

    async with factory() as s:
        deliveries = (await s.execute(select(NotificationDelivery))).scalars().all()
    assert len(deliveries) == 1


# =============================================================================
# 6. Unauthenticated → 401
# =============================================================================


async def test_list_channels_401_unauthenticated(unauthenticated_client):
    resp = await unauthenticated_client.get("/api/notifications/channels")
    assert resp.status_code == 401


async def test_post_channel_401_unauthenticated(unauthenticated_client):
    resp = await unauthenticated_client.post(
        "/api/notifications/channels",
        json={"bot_token": _BOT_TOKEN, "chat_id": _CHAT_ID},
    )
    assert resp.status_code == 401


async def test_delete_channel_401_unauthenticated(unauthenticated_client):
    resp = await unauthenticated_client.delete("/api/notifications/channels/1")
    assert resp.status_code == 401


async def test_test_channel_401_unauthenticated(unauthenticated_client):
    resp = await unauthenticated_client.post(
        "/api/notifications/channels/telegram/test",
        json={},
    )
    assert resp.status_code == 401


# ── § chat_id validation ──────────────────────────────────────────────────────


async def test_post_channel_negative_chat_id_accepted(notif_client):
    """A negative numeric chat_id (group/supergroup) must be accepted."""
    with (
        patch("finlytics.api.notifications.telegram_get_me", new=AsyncMock(return_value={"id": 1})),
        patch("finlytics.api.notifications.encrypt_token", return_value="ciphertext"),
    ):
        resp = await notif_client.post(
            "/api/notifications/channels",
            json={"bot_token": _BOT_TOKEN, "chat_id": "-1001234567890"},
        )
    assert resp.status_code == 201


async def test_post_channel_username_handle_rejected(notif_client):
    """@username is not a valid chat_id — must return 422."""
    resp = await notif_client.post(
        "/api/notifications/channels",
        json={"bot_token": _BOT_TOKEN, "chat_id": "@mychannel"},
    )
    assert resp.status_code == 422


async def test_post_channel_nonnumeric_chat_id_rejected(notif_client):
    """Letters-only chat_id must return 422."""
    resp = await notif_client.post(
        "/api/notifications/channels",
        json={"bot_token": _BOT_TOKEN, "chat_id": "notanumber"},
    )
    assert resp.status_code == 422


async def test_test_channel_username_handle_rejected(notif_client):
    """@username in TelegramTestIn.chat_id must also return 422."""
    resp = await notif_client.post(
        "/api/notifications/channels/telegram/test",
        json={"bot_token": _BOT_TOKEN, "chat_id": "@badhandle"},
    )
    assert resp.status_code == 422


async def test_test_channel_null_chat_id_accepted(notif_client):
    """Omitting chat_id in TelegramTestIn is valid (uses stored channel path)."""
    # Should fall through to "no stored channel" → 400, NOT a 422 validation error.
    resp = await notif_client.post(
        "/api/notifications/channels/telegram/test",
        json={"bot_token": _BOT_TOKEN},
    )
    assert resp.status_code == 400  # partial creds, not a validation error


# ── § message_thread_id (forum topics) ────────────────────────────────────────


async def test_post_channel_thread_id_stored_in_config(notif_client):
    """A thread ID on a group chat is accepted and lands in the encrypted blob."""
    with (
        patch("finlytics.api.notifications.telegram_get_me", new=AsyncMock(return_value={"id": 1})),
        patch(
            "finlytics.api.notifications.encrypt_token", return_value="ciphertext"
        ) as encrypt_mock,
    ):
        resp = await notif_client.post(
            "/api/notifications/channels",
            json={
                "bot_token": _BOT_TOKEN,
                "chat_id": "-1001234567890",
                "message_thread_id": 42,
            },
        )
    assert resp.status_code == 201
    stored = json.loads(encrypt_mock.call_args.args[0])
    assert stored["message_thread_id"] == 42


async def test_post_channel_without_thread_id_stores_null(notif_client):
    """Omitting the thread ID keeps the key present but null (general chat)."""
    with (
        patch("finlytics.api.notifications.telegram_get_me", new=AsyncMock(return_value={"id": 1})),
        patch(
            "finlytics.api.notifications.encrypt_token", return_value="ciphertext"
        ) as encrypt_mock,
    ):
        resp = await notif_client.post(
            "/api/notifications/channels",
            json={"bot_token": _BOT_TOKEN, "chat_id": "-1001234567890"},
        )
    assert resp.status_code == 201
    stored = json.loads(encrypt_mock.call_args.args[0])
    assert stored["message_thread_id"] is None


async def test_post_channel_thread_id_on_private_chat_rejected(notif_client):
    """Forum topics only exist in groups — a positive chat_id must return 422."""
    resp = await notif_client.post(
        "/api/notifications/channels",
        json={"bot_token": _BOT_TOKEN, "chat_id": "123456789", "message_thread_id": 42},
    )
    assert resp.status_code == 422


@pytest.mark.parametrize("thread_id", [0, -1])
async def test_post_channel_non_positive_thread_id_rejected(notif_client, thread_id):
    """A zero or negative thread ID is invalid."""
    resp = await notif_client.post(
        "/api/notifications/channels",
        json={
            "bot_token": _BOT_TOKEN,
            "chat_id": "-1001234567890",
            "message_thread_id": thread_id,
        },
    )
    assert resp.status_code == 422


async def test_test_channel_forwards_thread_id(notif_client):
    """The wizard preview send targets the requested topic."""
    with patch(
        "finlytics.api.notifications.telegram_send_message",
        new_callable=AsyncMock,
    ) as send_mock:
        resp = await notif_client.post(
            "/api/notifications/channels/telegram/test",
            json={
                "bot_token": _BOT_TOKEN,
                "chat_id": "-1001234567890",
                "message_thread_id": 42,
            },
        )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert send_mock.call_args.kwargs["message_thread_id"] == 42


async def test_test_channel_stored_thread_id_forwarded(sqlite_engine, notif_client):
    """The stored-channel path reads message_thread_id back out of the config blob."""
    async with _sf(sqlite_engine)() as s:
        s.add(_make_channel())
        await s.commit()

    config = json.dumps(
        {"bot_token": _BOT_TOKEN, "chat_id": "-1001234567890", "message_thread_id": 7}
    )
    with (
        patch("finlytics.api.notifications.decrypt_token", return_value=config),
        patch(
            "finlytics.api.notifications.telegram_send_message", new_callable=AsyncMock
        ) as send_mock,
    ):
        resp = await notif_client.post("/api/notifications/channels/telegram/test", json={})

    assert resp.status_code == 200
    assert send_mock.call_args.kwargs["message_thread_id"] == 7


async def test_test_channel_legacy_config_without_thread_id(sqlite_engine, notif_client):
    """Channels stored before this field existed still send (thread id → None)."""
    async with _sf(sqlite_engine)() as s:
        s.add(_make_channel())
        await s.commit()

    with (
        patch("finlytics.api.notifications.decrypt_token", return_value=_DECRYPTED_CONFIG),
        patch(
            "finlytics.api.notifications.telegram_send_message", new_callable=AsyncMock
        ) as send_mock,
    ):
        resp = await notif_client.post("/api/notifications/channels/telegram/test", json={})

    assert resp.status_code == 200
    assert send_mock.call_args.kwargs["message_thread_id"] is None
