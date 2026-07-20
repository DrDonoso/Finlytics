"""Notifications API router.

Routes
──────
  GET  /api/notifications               — evaluate + list active notifications
  GET  /api/notifications/unread-count  — cheap badge count (no evaluation)
  POST /api/notifications/read-all      — mark all unread as read
  POST /api/notifications/{id}/read     — mark one as read
  POST /api/notifications/{id}/dismiss  — dismiss one

  GET    /api/notifications/channels                  — list channels (no secrets)
  POST   /api/notifications/channels                  — upsert Telegram channel
  DELETE /api/notifications/channels/{id}             — remove channel
  POST   /api/notifications/channels/telegram/test    — test send

All routes are auth-gated at the router-registration level in app.py.
Notification state (read/dismiss) is backend-owned so it survives cross-device
access and Telegram delivery tracking (Slice 2).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import case, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from finlytics.api.deps import get_current_user, get_db
from finlytics.api.schemas import (
    NotificationChannelOut,
    NotificationOut,
    ReadAllOut,
    TelegramChannelIn,
    TelegramTestIn,
    TelegramTestOut,
    UnreadCountOut,
)
from finlytics.db.models import Notification, NotificationChannel
from finlytics.investments.crypto import EncryptionNotConfiguredError, decrypt_token, encrypt_token
from finlytics.notifications.service import evaluate_notifications
from finlytics.notifications.telegram import TelegramError, telegram_get_me, telegram_send_message

log = logging.getLogger(__name__)

router = APIRouter(prefix="/notifications", tags=["notifications"])

# Severity sort rank: lower = shown first
_SEVERITY_RANK = case({"warning": 0, "info": 1}, value=Notification.severity, else_=99)


def _to_out(n: Notification) -> NotificationOut:
    return NotificationOut(
        id=n.id,
        source=n.source,
        type=n.type,
        severity=n.severity,
        title_key=n.title_key,
        title_args=n.title_args,
        body_key=n.body_key,
        body_args=n.body_args,
        action_link=n.action_link,
        created_at=n.created_at,
        read_at=n.read_at,
        dismissed_at=n.dismissed_at,
    )


@router.get("", response_model=list[NotificationOut])
async def list_notifications(
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[NotificationOut]:
    """Evaluate all detectors, upsert results, return active notifications.

    Active = not dismissed AND not resolved.  Sorted: most-severe first,
    then newest first.  The badge counter uses /unread-count (cheaper).
    """
    await evaluate_notifications(db, user.id)

    result = await db.execute(
        select(Notification)
        .where(
            Notification.user_id == user.id,
            Notification.dismissed_at.is_(None),
            Notification.resolved_at.is_(None),
        )
        .order_by(_SEVERITY_RANK, Notification.created_at.desc())
    )
    rows = result.scalars().all()
    return [_to_out(n) for n in rows]


@router.get("/unread-count", response_model=UnreadCountOut)
async def unread_count(
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UnreadCountOut:
    """Return the count of unread active notifications (cheap — no evaluation).

    Safe to poll frequently for the bell badge.  Does NOT run detectors.
    Unread = read_at IS NULL AND dismissed_at IS NULL AND resolved_at IS NULL.
    """
    from sqlalchemy import func as sqlfunc

    result = await db.execute(
        select(sqlfunc.count()).select_from(
            select(Notification.id)
            .where(
                Notification.user_id == user.id,
                Notification.read_at.is_(None),
                Notification.dismissed_at.is_(None),
                Notification.resolved_at.is_(None),
            )
            .subquery()
        )
    )
    count = result.scalar_one()
    return UnreadCountOut(count=count)


# NOTE: /read-all must be registered BEFORE /{id}/read to prevent FastAPI
# from interpreting "read-all" as a path parameter.

@router.post("/read-all", response_model=ReadAllOut)
async def mark_all_read(
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ReadAllOut:
    """Mark all unread, active notifications as read for the current user."""
    now = datetime.now(timezone.utc)
    async with db.begin():
        result = await db.execute(
            update(Notification)
            .where(
                Notification.user_id == user.id,
                Notification.read_at.is_(None),
                Notification.dismissed_at.is_(None),
                Notification.resolved_at.is_(None),
            )
            .values(read_at=now, updated_at=now)
        )
    return ReadAllOut(updated=result.rowcount)


@router.post("/{notification_id}/read", status_code=204)
async def mark_read(
    notification_id: int,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Set read_at on a single notification (scoped to the current user)."""
    async with db.begin():
        result = await db.execute(
            select(Notification).where(
                Notification.id == notification_id,
                Notification.user_id == user.id,
            )
        )
        notif = result.scalar_one_or_none()
        if notif is None:
            raise HTTPException(status_code=404, detail="Notification not found")
        if notif.read_at is None:
            now = datetime.now(timezone.utc)
            notif.read_at = now
            notif.updated_at = now


@router.post("/{notification_id}/dismiss", status_code=204)
async def dismiss(
    notification_id: int,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Set dismissed_at on a notification (hides it from the active list).

    Dismissed rows are kept in the DB so Telegram never re-delivers them.
    """
    async with db.begin():
        result = await db.execute(
            select(Notification).where(
                Notification.id == notification_id,
                Notification.user_id == user.id,
            )
        )
        notif = result.scalar_one_or_none()
        if notif is None:
            raise HTTPException(status_code=404, detail="Notification not found")
        if notif.dismissed_at is None:
            now = datetime.now(timezone.utc)
            notif.dismissed_at = now
            notif.updated_at = now


# ── Channel CRUD ──────────────────────────────────────────────────────────────
# NOTE: /channels routes must be registered before /{notification_id}/... routes
# (all below are different paths so FastAPI doesn't confuse them, but
#  channels/telegram/test is registered before channels/{id} to be explicit).


def _to_channel_out(c: NotificationChannel) -> NotificationChannelOut:
    return NotificationChannelOut(
        id=c.id,
        channel=c.channel,
        label=c.label,
        enabled=c.enabled,
        created_at=c.created_at,
    )


@router.get("/channels", response_model=list[NotificationChannelOut])
async def list_channels(
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[NotificationChannelOut]:
    """Return the user's configured notification channels (no secrets)."""
    result = await db.execute(
        select(NotificationChannel).where(NotificationChannel.user_id == user.id)
    )
    channels = result.scalars().all()
    return [_to_channel_out(c) for c in channels]


@router.post("/channels", response_model=NotificationChannelOut, status_code=201)
async def upsert_telegram_channel(
    body: TelegramChannelIn,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> NotificationChannelOut:
    """Upsert the user's Telegram notification channel.

    Validates the bot_token via getMe before storing. Encrypts config at rest.
    One Telegram channel per user — POSTing again replaces the existing config.
    Returns a safe record (no secrets). Raises 400 on invalid token, 503 on
    missing encryption key.
    """
    # Validate token — safe error on failure (no token in message)
    try:
        await telegram_get_me(body.bot_token)
    except TelegramError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Encrypt config blob
    config_payload = json.dumps({"bot_token": body.bot_token, "chat_id": body.chat_id})
    try:
        config_enc = encrypt_token(config_payload)
    except EncryptionNotConfiguredError:
        raise HTTPException(
            status_code=503,
            detail="Server not configured for encryption — contact the administrator.",
        )

    # Masked label: last 4 chars of chat_id string
    chat_id_str = str(body.chat_id)
    label = f"Telegram · ••••{chat_id_str[-4:]}"

    now = datetime.now(timezone.utc)
    async with db.begin():
        result = await db.execute(
            select(NotificationChannel).where(
                NotificationChannel.user_id == user.id,
                NotificationChannel.channel == "telegram",
            )
        )
        channel = result.scalar_one_or_none()
        if channel is not None:
            channel.config_enc = config_enc
            channel.label = label
            channel.updated_at = now
        else:
            channel = NotificationChannel(
                user_id=user.id,
                channel="telegram",
                config_enc=config_enc,
                label=label,
                enabled=True,
                created_at=now,
                updated_at=now,
            )
            db.add(channel)
        await db.flush()

    return _to_channel_out(channel)


@router.post("/channels/telegram/test", response_model=TelegramTestOut)
async def test_telegram_channel(
    body: TelegramTestIn,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TelegramTestOut:
    """Send a test message to verify Telegram is wired up correctly.

    If body.bot_token + body.chat_id are provided, use those (wizard "test before
    save" flow). Otherwise use the stored channel. Returns HTTP 200 in all cases
    with ok=true/false — never leaks secrets in the response.
    """
    if body.bot_token and body.chat_id:
        bot_token = body.bot_token
        chat_id = body.chat_id
    elif body.bot_token or body.chat_id:
        raise HTTPException(
            status_code=400,
            detail="Provide both bot_token and chat_id, or neither (to use stored channel).",
        )
    else:
        # Use stored channel
        result = await db.execute(
            select(NotificationChannel).where(
                NotificationChannel.user_id == user.id,
                NotificationChannel.channel == "telegram",
            )
        )
        channel = result.scalar_one_or_none()
        if channel is None:
            raise HTTPException(status_code=400, detail="No Telegram channel configured.")
        if not channel.config_enc:
            raise HTTPException(
                status_code=400,
                detail="Channel config is missing — please re-configure the Telegram channel.",
            )
        try:
            config_data = json.loads(decrypt_token(channel.config_enc))
        except EncryptionNotConfiguredError:
            raise HTTPException(
                status_code=503,
                detail="Server not configured for encryption — contact the administrator.",
            )
        bot_token = config_data["bot_token"]
        chat_id = str(config_data["chat_id"])

    try:
        await telegram_send_message(
            bot_token,
            str(chat_id),
            "✅ Finlytics: notificaciones de Telegram configuradas correctamente.",
        )
        return TelegramTestOut(ok=True)
    except TelegramError as exc:
        return TelegramTestOut(ok=False, error=str(exc))


@router.delete("/channels/{channel_id}", status_code=204)
async def delete_channel(
    channel_id: int,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a notification channel (scoped to the current user). 404 if not owned."""
    async with db.begin():
        result = await db.execute(
            select(NotificationChannel).where(
                NotificationChannel.id == channel_id,
                NotificationChannel.user_id == user.id,
            )
        )
        channel = result.scalar_one_or_none()
        if channel is None:
            raise HTTPException(status_code=404, detail="Channel not found.")
        await db.delete(channel)
