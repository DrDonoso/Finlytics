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
from datetime import UTC, datetime
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import CursorResult, case, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from finlytics.api.deps import get_current_user, get_db
from finlytics.api.schemas import (
    ImportSummaryJobOut,
    ImportSummaryRetryIn,
    ImportSummarySettingsIn,
    ImportSummarySettingsOut,
    NotificationChannelOut,
    NotificationOut,
    ReadAllOut,
    TelegramChannelIn,
    TelegramTestIn,
    TelegramTestOut,
    UnreadCountOut,
)
from finlytics.config import settings
from finlytics.db.models import ImportSummarySettings, Notification, NotificationChannel, User
from finlytics.db.queries import import_summaries as summary_queries
from finlytics.extraction.llm_client import is_llm_configured
from finlytics.investments.crypto import EncryptionNotConfiguredError, decrypt_token, encrypt_token
from finlytics.notifications.import_summaries import summary_destination, wake_import_summaries
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
    now = datetime.now(UTC)
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
    return ReadAllOut(updated=cast("CursorResult[Any]", result).rowcount)


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
            now = datetime.now(UTC)
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
            now = datetime.now(UTC)
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
    config_payload = json.dumps(
        {
            "bot_token": body.bot_token,
            "chat_id": body.chat_id,
            "message_thread_id": body.message_thread_id,
        }
    )
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

    now = datetime.now(UTC)
    async with db.begin():
        await summary_queries.get_summary_settings(db, user.id, lock=True)
        result = await db.execute(
            select(NotificationChannel).where(
                NotificationChannel.user_id == user.id,
                NotificationChannel.channel == "telegram",
            )
        )
        channel = result.scalar_one_or_none()
        if channel is not None:
            await summary_queries.cancel_summaries(
                db, user.id, channel_id=channel.id, reason="configuration_changed",
            )
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
        message_thread_id = body.message_thread_id
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
        message_thread_id = config_data.get("message_thread_id")

    try:
        await telegram_send_message(
            bot_token,
            str(chat_id),
            "✅ Finlytics: notificaciones de Telegram configuradas correctamente.",
            message_thread_id=message_thread_id,
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
        preference = await summary_queries.get_summary_settings(db, user.id, lock=True)
        result = await db.execute(
            select(NotificationChannel).where(
                NotificationChannel.id == channel_id,
                NotificationChannel.user_id == user.id,
            )
        )
        channel = result.scalar_one_or_none()
        if channel is None:
            raise HTTPException(status_code=404, detail="Channel not found.")
        if preference is not None and preference.channel_id == channel_id:
            preference.enabled = False
            preference.channel_id = None
        await summary_queries.cancel_summaries(
            db, user.id, channel_id=channel_id, reason="channel_removed",
        )
        await db.delete(channel)


def _summary_settings_out(row: ImportSummarySettings | None) -> ImportSummarySettingsOut:
    return ImportSummarySettingsOut.model_validate({
        "enabled": row.enabled if row else False,
        "channel_id": row.channel_id if row else None,
        "language": row.language if row else "en",
        "ai_available": is_llm_configured(settings),
    })


@router.get("/import-summary-settings", response_model=ImportSummarySettingsOut)
async def get_import_summary_settings(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
) -> ImportSummarySettingsOut:
    return _summary_settings_out(await summary_queries.get_summary_settings(db, user.id))


@router.put("/import-summary-settings", response_model=ImportSummarySettingsOut)
async def put_import_summary_settings(
    body: ImportSummarySettingsIn,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
) -> ImportSummarySettingsOut:
    if body.enabled and not is_llm_configured(settings):
        raise HTTPException(status_code=503, detail="Configure AI before enabling import summaries.")
    async with db.begin():
        await db.execute(select(User.id).where(User.id == user.id).with_for_update())
        row = await summary_queries.get_summary_settings(db, user.id, lock=True)
        if body.channel_id is not None:
            channel = await summary_queries.get_summary_channel(db, user.id, body.channel_id)
            if channel is None:
                raise HTTPException(status_code=422, detail="Select an available notification channel.")
            if body.enabled:
                try:
                    summary_destination(channel)
                except EncryptionNotConfiguredError:
                    raise HTTPException(status_code=503, detail="Notification encryption is unavailable.")
                except TelegramError:
                    raise HTTPException(status_code=422, detail="Reconfigure the notification channel.")
        if row is None:
            row = ImportSummarySettings(user_id=user.id)
            db.add(row)
        elif (row.enabled, row.channel_id, row.language) != (
            body.enabled, body.channel_id, body.language,
        ):
            await summary_queries.cancel_summaries(
                db, user.id, reason="configuration_changed" if body.enabled else "disabled",
            )
        row.enabled = body.enabled
        row.channel_id = body.channel_id
        row.language = body.language
    return _summary_settings_out(row)


@router.get("/import-summaries", response_model=list[ImportSummaryJobOut])
async def list_import_summaries(
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
) -> list[ImportSummaryJobOut]:
    jobs = await summary_queries.list_summary_jobs(db, user.id, limit=limit)
    return [ImportSummaryJobOut.model_validate(job, from_attributes=True) for job in jobs]


@router.post("/import-summaries/{job_id}/retry", response_model=ImportSummaryJobOut)
async def retry_import_summary(
    job_id: int, body: ImportSummaryRetryIn,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
) -> ImportSummaryJobOut:
    async with db.begin():
        try:
            job = await summary_queries.retry_summary(
                db, user.id, job_id, acknowledge_uncertain=body.acknowledge_uncertain,
            )
        except summary_queries.SummaryConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        if job is None:
            raise HTTPException(status_code=404, detail="Import summary not found.")
    wake_import_summaries()
    return ImportSummaryJobOut.model_validate(job, from_attributes=True)
