"""Unit tests for deliver_new (Slice 2 delivery seam).

Uses in-memory SQLite so these tests are self-contained.

Coverage:
  - deliver_new is a no-op when new_notifs is empty
  - deliver_new is a no-op when no channels exist
  - A new notification with a configured channel gets a delivery record (sent)
  - Calling deliver_new twice with the same notification does NOT double-send
    (idempotency guard: second call skips, telegram_send_message called once)
  - A Telegram failure records status='failed' without raising
  - telegram_send_enabled=False is a complete no-op
  - Config encryption roundtrip: encrypt_token → decrypt_token
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from finlytics.db.models import (
    Base,
    Notification,
    NotificationChannel,
    NotificationDelivery,
)
from finlytics.investments.crypto import decrypt_token, encrypt_token
from finlytics.notifications.service import deliver_new
from finlytics.notifications.telegram import TelegramError

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
# Valid Fernet key: base64.urlsafe_b64encode(b"\x00" * 32)
_FERNET_KEY = "A" * 43 + "="

# ── Fixtures ──────────────────────────────────────────────────────────────────


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


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _insert_notification(db: AsyncSession) -> Notification:
    notif = Notification(
        user_id=1,
        source="test",
        type="test_condition",
        severity="info",
        dedup_key=f"test:condition:{_now().timestamp()}",
        title_key="notif.statement_missing",
        title_args={"account": "BBVA", "month": "2026-06"},
        created_at=_now(),
        updated_at=_now(),
    )
    async with db.begin():
        db.add(notif)
        await db.flush()
    return notif


async def _insert_channel(db: AsyncSession, user_id: int = 1) -> NotificationChannel:
    """Insert a channel with a dummy config_enc (decrypt is mocked in most tests)."""
    channel = NotificationChannel(
        user_id=user_id,
        channel="telegram",
        config_enc="dummy_encrypted_config",
        label="Telegram · ••••6789",
        enabled=True,
        created_at=_now(),
        updated_at=_now(),
    )
    async with db.begin():
        db.add(channel)
        await db.flush()
    return channel


_DECRYPTED_CONFIG = json.dumps({"bot_token": "test_bot_token", "chat_id": "123456789"})


# ── Tests ─────────────────────────────────────────────────────────────────────


async def test_no_op_when_empty_notifs(db: AsyncSession):
    """deliver_new with empty list should not touch the DB at all."""
    await deliver_new(db, user_id=1, new_notifs=[])
    result = await db.execute(select(NotificationDelivery))
    assert result.scalars().all() == []


async def test_no_op_when_no_channels(db: AsyncSession):
    """deliver_new skips when no channels are configured for the user."""
    notif = await _insert_notification(db)
    with patch("finlytics.notifications.service.telegram_send_message") as mock_send:
        await deliver_new(db, user_id=1, new_notifs=[notif])
        mock_send.assert_not_called()

    result = await db.execute(select(NotificationDelivery))
    assert result.scalars().all() == []


async def test_delivery_creates_sent_record(db: AsyncSession):
    """A notification with a configured channel produces a 'sent' delivery record."""
    notif = await _insert_notification(db)
    await _insert_channel(db, user_id=1)

    with (
        patch(
            "finlytics.notifications.service.decrypt_token",
            return_value=_DECRYPTED_CONFIG,
        ),
        patch(
            "finlytics.notifications.service.telegram_send_message",
            new_callable=AsyncMock,
        ) as mock_send,
    ):
        await deliver_new(db, user_id=1, new_notifs=[notif])

    mock_send.assert_called_once()
    # Verify message text contains expected content and NOT the bot_token
    call_text = mock_send.call_args.args[2]
    assert "BBVA" in call_text
    assert "test_bot_token" not in call_text

    rows = (await db.execute(select(NotificationDelivery))).scalars().all()
    assert len(rows) == 1
    assert rows[0].status == "sent"
    assert rows[0].sent_at is not None
    assert rows[0].channel == "telegram"
    assert rows[0].notification_id == notif.id


async def test_idempotency_no_double_send(db: AsyncSession):
    """Calling deliver_new twice for the same notification sends exactly once."""
    notif = await _insert_notification(db)
    await _insert_channel(db, user_id=1)

    with (
        patch(
            "finlytics.notifications.service.decrypt_token",
            return_value=_DECRYPTED_CONFIG,
        ),
        patch(
            "finlytics.notifications.service.telegram_send_message",
            new_callable=AsyncMock,
        ) as mock_send,
    ):
        await deliver_new(db, user_id=1, new_notifs=[notif])
        await deliver_new(db, user_id=1, new_notifs=[notif])

    mock_send.assert_called_once()  # second call skips — already delivered

    rows = (await db.execute(select(NotificationDelivery))).scalars().all()
    assert len(rows) == 1  # still only one delivery record
    assert rows[0].status == "sent"


async def test_failed_send_records_error_no_raise(db: AsyncSession):
    """A TelegramError records status='failed' and does NOT propagate."""
    notif = await _insert_notification(db)
    await _insert_channel(db, user_id=1)

    with (
        patch(
            "finlytics.notifications.service.decrypt_token",
            return_value=_DECRYPTED_CONFIG,
        ),
        patch(
            "finlytics.notifications.service.telegram_send_message",
            new_callable=AsyncMock,
            side_effect=TelegramError("sendMessage failed (HTTP 403)."),
        ),
    ):
        # Must NOT raise
        await deliver_new(db, user_id=1, new_notifs=[notif])

    rows = (await db.execute(select(NotificationDelivery))).scalars().all()
    assert len(rows) == 1
    assert rows[0].status == "failed"
    assert "403" in (rows[0].error or "")
    assert rows[0].sent_at is None


async def test_send_enabled_false_skips(db: AsyncSession, monkeypatch):
    """When telegram_send_enabled=False, deliver_new is a complete no-op."""
    notif = await _insert_notification(db)
    await _insert_channel(db, user_id=1)

    from finlytics.config import settings as real_settings
    monkeypatch.setattr(real_settings, "telegram_send_enabled", False)

    with patch(
        "finlytics.notifications.service.telegram_send_message",
        new_callable=AsyncMock,
    ) as mock_send:
        await deliver_new(db, user_id=1, new_notifs=[notif])

    mock_send.assert_not_called()
    result = await db.execute(select(NotificationDelivery))
    assert result.scalars().all() == []


async def test_config_encryption_roundtrip(monkeypatch):
    """encrypt_token / decrypt_token roundtrip preserves secrets and hides them in ciphertext."""
    from finlytics.config import settings as real_settings
    monkeypatch.setattr(real_settings, "finlytics_encryption_key", _FERNET_KEY)

    config_in = {"bot_token": "super_secret_token", "chat_id": "-100123456789"}
    payload = json.dumps(config_in)
    ciphertext = encrypt_token(payload)
    plaintext = decrypt_token(ciphertext)
    config_out = json.loads(plaintext)

    assert config_out["bot_token"] == config_in["bot_token"]
    assert config_out["chat_id"] == config_in["chat_id"]
    # Ciphertext must NOT expose the secret in plaintext
    assert config_in["bot_token"] not in ciphertext
